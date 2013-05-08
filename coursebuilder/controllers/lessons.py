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

import datetime
import urllib
import urlparse

from models import models
from models import student_work
from models import transforms
from models.config import ConfigProperty
from models.counters import PerfCounter
from models.review import ReviewUtils
from models.roles import Roles
from models.student_work import StudentWorkUtils
from modules.review import domain
from tools import verify

from utils import BaseHandler
from utils import BaseRESTHandler
from utils import CAN_PERSIST_PAGE_EVENTS
from utils import HUMAN_READABLE_DATETIME_FORMAT
from utils import XsrfTokenManager

from google.appengine.ext import db

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

UNIT_PAGE_TYPE = 'unit'
ACTIVITY_PAGE_TYPE = 'activity'


def extract_unit_and_lesson(handler):
    """Loads unit and lesson specified in the request."""

    # Finds unit requested or a first unit in the course.
    u = handler.request.get('unit')
    unit = handler.get_course().find_unit_by_id(u)
    if not unit:
        units = handler.get_course().get_units()
        for current_unit in units:
            if verify.UNIT_TYPE_UNIT == current_unit.type:
                unit = current_unit
                break
    if not unit:
        return None, None

    # Find lesson requested or a first lesson in the unit.
    l = handler.request.get('lesson')
    lesson = None
    lessons = handler.get_course().get_lessons(unit.unit_id)
    if not l:
        if lessons:
            lesson = lessons[0]
    else:
        lesson = handler.get_course().find_lesson_by_id(unit, l)
    return unit, lesson


def get_unit_and_lesson_id_from_url(url):
    """Extracts unit and lesson ids from a URL."""
    url_components = urlparse.urlparse(url)
    query_dict = urlparse.parse_qs(url_components.query)
    unit_id, lesson_id = query_dict['unit'][0], query_dict['lesson'][0]
    return unit_id, lesson_id


def create_readonly_assessment_params(content, answers):
    """Creates parameters for a readonly assessment in the view templates."""
    assessment_params = {
        'preamble': content['assessment']['preamble'],
        'questionsList': content['assessment']['questionsList'],
        'answers': answers,
    }
    return assessment_params


class CourseHandler(BaseHandler):
    """Handler for generating course page."""

    @classmethod
    def get_child_routes(cls):
        """Add child handlers for REST."""
        return [('/rest/events', EventsRESTHandler)]

    def augment_assessment_units(self, student):
        """Adds additional fields to assessment units."""
        course = self.get_course()
        rp = course.get_reviews_processor()

        for unit in self.template_value['units']:
            if unit.type == 'A':
                unit.needs_human_grader = course.needs_human_grader(unit)
                if unit.needs_human_grader:
                    review_steps = rp.get_review_steps_by(
                        unit.unit_id, student.get_key())
                    review_min_count = unit.workflow.get_review_min_count()

                    unit.matcher = unit.workflow.get_matcher()
                    unit.review_progress = ReviewUtils.get_review_progress(
                        review_steps, review_min_count,
                        course.get_progress_tracker()
                    )

                    unit.is_submitted = rp.does_submission_exist(
                        unit.unit_id, student.get_key())

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
        self.augment_assessment_units(student)

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
        unit, lesson = extract_unit_and_lesson(self)
        unit_id = unit.unit_id

        # If the unit is not currently available, and the user is not an admin,
        # redirect to the main page.
        if (not unit.now_available and
            not Roles.is_course_admin(self.app_context)):
            self.redirect('/')
            return

        # Set template values for nav bar and page type.
        self.template_value['navbar'] = {'course': True}
        self.template_value['page_type'] = UNIT_PAGE_TYPE

        lessons = self.get_lessons(unit_id)

        # Set template values for a unit and its lesson entities
        self.template_value['unit'] = unit
        self.template_value['unit_id'] = unit_id
        self.template_value['lesson'] = lesson

        if lesson:
            self.template_value['objectives'] = lesson.objectives

        self.template_value['lessons'] = lessons

        # If this unit contains no lessons, return.
        if not lesson:
            self.render('unit.html')
            return

        lesson_id = lesson.lesson_id
        self.template_value['lesson_id'] = lesson_id

        index = lesson.index - 1  # indexes are 1-based

        # Format back button.
        if index == 0:
            self.template_value['back_button_url'] = ''
        else:
            prev_lesson = lessons[index - 1]
            if prev_lesson.activity:
                self.template_value['back_button_url'] = (
                    'activity?unit=%s&lesson=%s' % (
                        unit_id, prev_lesson.lesson_id))
            else:
                self.template_value['back_button_url'] = (
                    'unit?unit=%s&lesson=%s' % (unit_id, prev_lesson.lesson_id))

        # Format next button.
        if lesson.activity:
            self.template_value['next_button_url'] = (
                'activity?unit=%s&lesson=%s' % (
                    unit_id, lesson_id))
        else:
            if not index < len(lessons) - 1:
                self.template_value['next_button_url'] = ''
            else:
                next_lesson = lessons[index + 1]
                self.template_value['next_button_url'] = (
                    'unit?unit=%s&lesson=%s' % (
                        unit_id, next_lesson.lesson_id))

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
        unit, lesson = extract_unit_and_lesson(self)
        unit_id = unit.unit_id

        # If the unit is not currently available, and the user is not an admin,
        # redirect to the main page.
        if (not unit.now_available and
            not Roles.is_course_admin(self.app_context)):
            self.redirect('/')
            return

        # Set template values for nav bar and page type.
        self.template_value['navbar'] = {'course': True}
        self.template_value['page_type'] = ACTIVITY_PAGE_TYPE

        lessons = self.get_lessons(unit_id)

        # Set template values for a unit and its lesson entities
        self.template_value['unit'] = unit
        self.template_value['unit_id'] = unit_id
        self.template_value['lesson'] = lesson
        self.template_value['lessons'] = lessons

        # If this unit contains no lessons, return.
        if not lesson:
            self.render('activity.html')
            return

        lesson_id = lesson.lesson_id
        self.template_value['lesson_id'] = lesson_id
        self.template_value['activity_script_src'] = (
            self.get_course().get_activity_filename(unit_id, lesson_id))

        index = lesson.index - 1  # indexes are 1-based

        # Format back button.
        self.template_value['back_button_url'] = (
            'unit?unit=%s&lesson=%s' % (unit_id, lesson_id))

        # Format next button.
        if not index < len(lessons) - 1:
            self.template_value['next_button_url'] = ''
        else:
            next_lesson = lessons[index + 1]
            self.template_value['next_button_url'] = (
                'unit?unit=%s&lesson=%s' % (
                    unit_id, next_lesson.lesson_id))

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
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        # Extract incoming args
        unit_id = self.request.get('name')
        course = self.get_course()
        unit = course.find_unit_by_id(unit_id)
        if not unit:
            self.error(404)
            return

        self.template_value['navbar'] = {'course': True}
        self.template_value['unit_id'] = unit_id
        self.template_value['record_events'] = CAN_PERSIST_ACTIVITY_EVENTS.value
        self.template_value['assessment_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('assessment-post'))
        self.template_value['event_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('event-post'))

        self.template_value['grader'] = unit.workflow.get_grader()

        readonly_view = False
        due_date_exceeded = False

        submission_due_date = unit.workflow.get_submission_due_date()
        if submission_due_date:
            self.template_value['submission_due_date'] = (
                submission_due_date.strftime(HUMAN_READABLE_DATETIME_FORMAT))

            time_now = datetime.datetime.now()
            if time_now > submission_due_date:
                readonly_view = True
                due_date_exceeded = True
                self.template_value['due_date_exceeded'] = True

        if course.needs_human_grader(unit):
            self.template_value['matcher'] = unit.workflow.get_matcher()

            rp = course.get_reviews_processor()
            review_steps_by = rp.get_review_steps_by(
                unit.unit_id, student.get_key())

            # Determine if the student can see others' reviews of his/her work.
            if (ReviewUtils.has_completed_enough_reviews(
                    review_steps_by, unit.workflow.get_review_min_count())):
                submission_and_review_steps = (
                    rp.get_submission_and_review_steps(
                        unit.unit_id, student.get_key()))

                submission_contents = submission_and_review_steps[0]
                review_steps_for = submission_and_review_steps[1]

                review_keys_for_student = []
                for review_step in review_steps_for:
                    can_show_review = (
                        review_step.state == domain.REVIEW_STATE_COMPLETED
                        and not review_step.removed
                        and review_step.review_key
                    )

                    if can_show_review:
                        review_keys_for_student.append(review_step.review_key)

                reviews_for_student = rp.get_reviews_by_keys(
                    unit.unit_id, review_keys_for_student)

                self.template_value['reviews_received'] = [
                    create_readonly_assessment_params(
                        course.get_review_form_content(unit),
                        StudentWorkUtils.get_answer_list(review)
                    ) for review in reviews_for_student]
            else:
                submission_contents = student_work.Submission.get_contents(
                    unit.unit_id, student.get_key())

            # Determine whether to show the assessment in readonly mode.
            if submission_contents or due_date_exceeded:
                readonly_view = True
                self.template_value['readonly_student_assessment'] = (
                    create_readonly_assessment_params(
                        course.get_assessment_content(unit),
                        StudentWorkUtils.get_answer_list(submission_contents)
                    )
                )

        if not readonly_view:
            self.template_value['assessment_script_src'] = (
                self.get_course().get_assessment_filename(unit_id))

            # If a previous submission exists, reinstate it.
            submission_contents = student_work.Submission.get_contents(
                unit.unit_id, student.get_key())
            saved_answers = (
                StudentWorkUtils.get_answer_list(submission_contents)
                if submission_contents else [])
            self.template_value['saved_answers'] = transforms.dumps(
                saved_answers)

        self.render('assessment.html')


class ReviewDashboardHandler(BaseHandler):
    """Handler for generating the index of reviews that a student has to do."""

    def populate_template(self, unit, review_steps):
        """Adds variables to the template for the review dashboard."""
        self.template_value['assessment_name'] = unit.title
        self.template_value['unit_id'] = unit.unit_id
        self.template_value['event_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('event-post'))
        self.template_value['review_dashboard_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('review-dashboard-post'))

        self.template_value['REVIEW_STATE_COMPLETED'] = (
            domain.REVIEW_STATE_COMPLETED)

        self.template_value['review_steps'] = review_steps
        self.template_value['review_min_count'] = (
            unit.workflow.get_review_min_count())

        review_due_date = unit.workflow.get_review_due_date()
        if review_due_date:
            self.template_value['review_due_date'] = review_due_date.strftime(
                HUMAN_READABLE_DATETIME_FORMAT)

        time_now = datetime.datetime.now()
        self.template_value['due_date_exceeded'] = (time_now > review_due_date)

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        course = self.get_course()
        rp = course.get_reviews_processor()
        unit, _ = extract_unit_and_lesson(self)
        if not unit:
            self.error(404)
            return

        self.template_value['navbar'] = {'course': True}

        if not course.needs_human_grader(unit):
            self.error(404)
            return

        # Check that the student has submitted the corresponding assignment.
        if not rp.does_submission_exist(unit.unit_id, student.get_key()):
            self.template_value['error_code'] = (
                'cannot_review_before_submitting_assignment')
            self.render('error.html')
            return

        review_steps = rp.get_review_steps_by(unit.unit_id, student.get_key())

        self.populate_template(unit, review_steps)
        required_review_count = unit.workflow.get_review_min_count()

        # The student can request a new submission if:
        # - all his/her current reviews are in Draft/Completed state, and
        # - he/she is not in the state where the required number of reviews
        #       has already been requested, but not all of these are completed.
        self.template_value['can_request_new_review'] = (
            len(review_steps) < required_review_count or
            ReviewUtils.has_completed_all_assigned_reviews(review_steps)
        )
        self.render('review_dashboard.html')

    def post(self):
        """Allows a reviewer to request a new review."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not self.assert_xsrf_token_or_fail(
                self.request, 'review-dashboard-post'):
            return

        course = self.get_course()
        unit, unused_lesson = extract_unit_and_lesson(self)
        if not unit:
            self.error(404)
            return

        rp = course.get_reviews_processor()
        review_steps = rp.get_review_steps_by(unit.unit_id, student.get_key())
        self.template_value['navbar'] = {'course': True}

        if not course.needs_human_grader(unit):
            self.error(404)
            return

        # Check that the student has submitted the corresponding assignment.
        if not rp.does_submission_exist(unit.unit_id, student.get_key()):
            self.template_value['error_code'] = (
                'cannot_review_before_submitting_assignment')
            self.render('error.html')
            return

        # Check that the review due date has not passed.
        time_now = datetime.datetime.now()
        review_due_date = unit.workflow.get_review_due_date()
        if time_now > review_due_date:
            self.template_value['error_code'] = (
                'cannot_request_review_after_deadline')
            self.render('error.html')
            return

        # Check that the student can request a new review.
        review_min_count = unit.workflow.get_review_min_count()
        can_request_new_review = (
            len(review_steps) < review_min_count or
            ReviewUtils.has_completed_all_assigned_reviews(review_steps))
        if not can_request_new_review:
            self.template_value['review_min_count'] = review_min_count
            self.template_value['error_code'] = 'must_complete_more_reviews'
            self.render('error.html')
            return

        self.template_value['no_submissions_available'] = True

        try:
            review_step_key = rp.get_new_review(unit.unit_id, student.get_key())
            redirect_params = {
                'key': review_step_key,
                'unit': unit.unit_id,
            }
            self.redirect('/review?%s' % urllib.urlencode(redirect_params))
        except Exception:  # pylint: disable-msg=broad-except
            review_steps = rp.get_review_steps_by(
                unit.unit_id, student.get_key())
            self.populate_template(unit, review_steps)
            self.render('review_dashboard.html')


class ReviewHandler(BaseHandler):
    """Handler for generating the submission page for individual reviews."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        course = self.get_course()
        rp = course.get_reviews_processor()
        unit, unused_lesson = extract_unit_and_lesson(self)

        if not course.needs_human_grader(unit):
            self.error(404)
            return

        review_step_key = self.request.get('key')
        if not unit or not review_step_key:
            self.error(404)
            return

        try:
            review_step_key = db.Key(encoded=review_step_key)
            review_step = rp.get_review_steps_by_keys(
                unit.unit_id, [review_step_key])[0]
        except Exception:  # pylint: disable-msg=broad-except
            self.error(404)
            return

        if not review_step:
            self.error(404)
            return

        # Check that the student is allowed to review this submission.
        if not student.has_same_key_as(review_step.reviewer_key):
            self.error(404)
            return

        self.template_value['navbar'] = {'course': True}
        self.template_value['unit_id'] = unit.unit_id
        self.template_value['key'] = review_step_key

        submission_key = review_step.submission_key
        submission_contents = student_work.Submission.get_contents_by_key(
            submission_key)

        readonly_student_assessment = create_readonly_assessment_params(
            course.get_assessment_content(unit),
            StudentWorkUtils.get_answer_list(submission_contents)
        )
        self.template_value['readonly_student_assessment'] = (
            readonly_student_assessment
        )

        review_due_date = unit.workflow.get_review_due_date()
        if review_due_date:
            self.template_value['review_due_date'] = review_due_date.strftime(
                HUMAN_READABLE_DATETIME_FORMAT)

        review_key = review_step.review_key
        rev = rp.get_reviews_by_keys(
            unit.unit_id, [review_key])[0] if review_key else None

        time_now = datetime.datetime.now()
        show_readonly_review = (
            review_step.state == domain.REVIEW_STATE_COMPLETED or
            time_now > review_due_date)

        self.template_value['due_date_exceeded'] = (time_now > review_due_date)

        if show_readonly_review:
            readonly_review_form = create_readonly_assessment_params(
                course.get_review_form_content(unit),
                StudentWorkUtils.get_answer_list(rev)
            )
            self.template_value['readonly_review_form'] = readonly_review_form
        else:
            # Populate the review form,
            self.template_value['assessment_script_src'] = (
                self.get_course().get_review_form_filename(unit.unit_id))
            saved_answers = (StudentWorkUtils.get_answer_list(rev)
                             if rev else [])
            self.template_value['saved_answers'] = transforms.dumps(
                saved_answers)

        self.template_value['record_events'] = CAN_PERSIST_ACTIVITY_EVENTS.value
        self.template_value['assessment_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('review-post'))
        self.template_value['event_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('event-post'))

        self.render('review.html')

    def post(self):
        """Handles POST requests, when a reviewer submits a review."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        course = self.get_course()
        rp = course.get_reviews_processor()

        unit_id = self.request.get('unit_id')
        unit = self.find_unit_by_id(unit_id)
        if not unit or not course.needs_human_grader(unit):
            self.error(404)
            return

        review_step_key = self.request.get('key')
        if not review_step_key:
            self.error(404)
            return

        try:
            review_step_key = db.Key(encoded=review_step_key)
            review_step = rp.get_review_steps_by_keys(
                unit.unit_id, [review_step_key])[0]
        except Exception:  # pylint: disable-msg=broad-except
            self.error(404)
            return

        # Check that the student is allowed to review this submission.
        if not student.has_same_key_as(review_step.reviewer_key):
            self.error(404)
            return

        self.template_value['navbar'] = {'course': True}
        self.template_value['unit_id'] = unit.unit_id

        # Check that the review due date has not passed.
        time_now = datetime.datetime.now()
        review_due_date = unit.workflow.get_review_due_date()
        if time_now > review_due_date:
            self.template_value['time_now'] = time_now.strftime(
                HUMAN_READABLE_DATETIME_FORMAT)
            self.template_value['review_due_date'] = (
                review_due_date.strftime(HUMAN_READABLE_DATETIME_FORMAT))
            self.template_value['error_code'] = 'review_deadline_exceeded'
            self.render('error.html')
            return

        mark_completed = (self.request.get('is_draft') == 'false')
        self.template_value['is_draft'] = (not mark_completed)

        review_payload = self.request.get('answers')
        review_payload = transforms.loads(
            review_payload) if review_payload else []
        try:
            rp.write_review(
                unit.unit_id, review_step_key, review_payload, mark_completed)
        except domain.TransitionError:
            self.template_value['error_code'] = 'review_already_submitted'
            self.render('error.html')
            return

        self.render('review_confirmation.html')


class EventsRESTHandler(BaseRESTHandler):
    """Provides REST API for an Event."""

    def post(self):
        """Receives event and puts it into datastore."""

        COURSE_EVENTS_RECEIVED.inc()
        can = CAN_PERSIST_ACTIVITY_EVENTS.value or CAN_PERSIST_PAGE_EVENTS.value
        if not can:
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
