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
from common import tags
from models import models
from models import transforms
from models.config import ConfigProperty
from models.counters import PerfCounter
from models.models import Student
from models.review import ReviewUtils
from models.roles import Roles
from tools import verify

from utils import BaseHandler
from utils import BaseRESTHandler
from utils import CAN_PERSIST_PAGE_EVENTS
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

UNIT_PAGE_TYPE = 'unit'
ACTIVITY_PAGE_TYPE = 'activity'

# Date format string for displaying the month (in words), day, four-digit year,
# hour and minute. Example: Mar 21 2013 at 13:00 UTC.
HUMAN_READABLE_DATE_FORMAT = '%b %d %Y, %H:%M UTC'


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
        reviews_processor = course.get_reviews_processor()

        for unit in self.template_value['units']:
            if unit.type == 'A':
                unit.needs_human_grader = course.needs_human_grader(unit)
                if unit.needs_human_grader:
                    reviews = reviews_processor.get_reviewer_reviews(
                        student, unit)
                    review_min_count = unit.workflow.get_review_min_count()

                    unit.matcher = unit.workflow.get_matcher()
                    unit.review_progress = ReviewUtils.get_review_progress(
                        reviews, review_min_count, course.get_progress_tracker()
                    )

                    unit.is_submitted = bool(
                        reviews_processor.get_student_work(student, unit))

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
            self.template_value[
                'gcb_can_use_dynamic_tags'] = tags.CAN_USE_DYNAMIC_TAGS.value
            if tags.CAN_USE_DYNAMIC_TAGS.value:
                objectives = tags.html_to_safe_dom(lesson.objectives)
            else:
                objectives = lesson.objectives
            self.template_value['objectives'] = objectives

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
        self.template_value['navbar'] = {'course': True}
        self.template_value['unit_id'] = unit_id
        self.template_value['record_events'] = CAN_PERSIST_ACTIVITY_EVENTS.value
        self.template_value['assessment_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('assessment-post'))
        self.template_value['event_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('event-post'))

        self.template_value['grader'] = unit.workflow.get_grader()
        self.template_value['matcher'] = unit.workflow.get_matcher()

        submission_due_date = unit.workflow.get_submission_due_date()
        if submission_due_date:
            self.template_value['submission_due_date'] = (
                submission_due_date.strftime(HUMAN_READABLE_DATE_FORMAT))

        readonly_view = False
        if course.needs_human_grader(unit):
            student_work = course.get_reviews_processor().get_student_work(
                student, unit)
            if student_work:
                readonly_view = True
                readonly_student_assessment = create_readonly_assessment_params(
                    course.get_assessment_content(unit),
                    ReviewUtils.get_answer_list(student_work['submission'])
                )
                self.template_value['readonly_student_assessment'] = (
                    readonly_student_assessment
                )

            reviews_processor = course.get_reviews_processor()
            reviews = reviews_processor.get_reviewer_reviews(student, unit)

            # Determine if the student can see others' reviews of his/her work.
            if (ReviewUtils.has_completed_enough_reviews(
                    reviews, unit.workflow.get_review_min_count())):
                reviewers = reviews_processor.get_student_work(
                    student, unit).get('reviewers')

                reviews_received = []
                for (unused_reviewer, review) in reviewers.iteritems():
                    if not review['is_draft']:
                        reviews_received.append(review['review'])

                self.template_value['reviews_received'] = [
                    create_readonly_assessment_params(
                        course.get_review_form_content(unit), review
                    ) for review in reviews_received]

        if not readonly_view:
            self.template_value['assessment_script_src'] = (
                self.get_course().get_assessment_filename(unit_id))

        self.render('assessment.html')


class ReviewHandler(BaseHandler):
    """Handler for generating the submission page for individual reviews."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        course = self.get_course()
        unit, unused_lesson = extract_unit_and_lesson(self)

        try:
            review_index = int(self.request.get('review_index'))
        except ValueError:
            self.error(404)
            return

        reviews = course.get_reviews_processor().get_reviewer_reviews(
            student, unit)
        if review_index >= len(reviews):
            self.error(404)
            return

        self.template_value['navbar'] = {'course': True}
        self.template_value['unit_id'] = unit.unit_id

        readonly_student_assessment = create_readonly_assessment_params(
            course.get_assessment_content(unit),
            ReviewUtils.get_answer_list(reviews[review_index]['submission'])
        )

        self.template_value['readonly_student_assessment'] = (
            readonly_student_assessment
        )

        self.template_value['review_index'] = review_index

        review_due_date = unit.workflow.get_review_due_date()
        if review_due_date:
            self.template_value['review_due_date'] = review_due_date.strftime(
                HUMAN_READABLE_DATE_FORMAT)

        if not reviews[review_index]['is_draft']:
            readonly_review_form = create_readonly_assessment_params(
                course.get_review_form_content(unit),
                reviews[review_index]['review'],
            )
            self.template_value['readonly_review_form'] = readonly_review_form
        else:
            # Populate the review form,
            self.template_value['assessment_script_src'] = (
                self.get_course().get_review_form_filename(unit.unit_id))
            self.template_value['saved_answers'] = transforms.dumps(
                reviews[review_index]['review'])

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
        unit_id = self.request.get('unit_id')
        unit = self.find_unit_by_id(unit_id)

        try:
            review_index = int(self.request.get('review_index'))
        except ValueError:
            return

        is_draft = (self.request.get('is_draft') == 'true')

        self.template_value['navbar'] = {'course': True}
        self.template_value['unit_id'] = unit.unit_id
        self.template_value['is_draft'] = is_draft

        reviews_processor = course.get_reviews_processor()

        reviews = reviews_processor.get_reviewer_reviews(student, unit)

        review_data = self.request.get('answers')
        review_data = transforms.loads(review_data) if review_data else []

        # Currently we only keep track of the answers to the review form, and
        # do not apply a scoring mechanism.
        review_data = ReviewUtils.get_answer_list(review_data)

        reviews_processor.submit_review(
            Student.get_by_email(reviews[review_index]['student']),
            unit, student, review_data, is_draft)

        self.render('review_confirmation.html')


class ReviewDashboardHandler(BaseHandler):
    """Handler for generating the index of reviews that a student has to do."""

    def populate_template(self, unit, reviews):
        """Adds variables to the template for the review dashboard."""
        self.template_value['navbar'] = {'course': True}
        self.template_value['assessment_name'] = unit.title
        self.template_value['unit_id'] = unit.unit_id
        self.template_value['event_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('event-post'))
        self.template_value['review_dashboard_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('review-dashboard-post'))

        self.template_value['reviews'] = reviews
        self.template_value['review_min_count'] = (
            unit.workflow.get_review_min_count())

        review_due_date = unit.workflow.get_review_due_date()
        if review_due_date:
            self.template_value['review_due_date'] = review_due_date.strftime(
                HUMAN_READABLE_DATE_FORMAT)

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        course = self.get_course()
        unit, unused_lesson = extract_unit_and_lesson(self)
        reviews = course.get_reviews_processor().get_reviewer_reviews(
            student, unit)

        # Check that the student has submitted the corresponding assignment.
        if not course.get_reviews_processor().get_student_work(student, unit):
            self.error(403)
            return

        self.populate_template(unit, reviews)
        required_review_count = unit.workflow.get_review_min_count()

        # The student can request a new submission if:
        # - all his/her current reviews are in Draft/Completed state, and
        # - he/she is not in the state where the required number of reviews
        #       has already been requested, but not all of these are completed.
        self.template_value['can_request_new_review'] = (
            not ReviewUtils.has_unstarted_reviews(reviews) and
            (len(reviews) < required_review_count or
             ReviewUtils.has_completed_all_assigned_reviews(reviews))
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
        reviews_processor = course.get_reviews_processor()

        reviews = course.get_reviews_processor().get_reviewer_reviews(
            student, unit)

        self.template_value['no_submissions_available'] = True

        if not ReviewUtils.has_unstarted_reviews(reviews):
            reviewee_id = reviews_processor.get_new_submission_for_review(
                student, unit)
            if reviewee_id:
                reviewee = Student.get_by_email(reviewee_id)
                reviews_processor.add_reviewer(reviewee, unit, student)
                self.template_value['no_submissions_available'] = False
            reviews = course.get_reviews_processor().get_reviewer_reviews(
                student, unit)

        self.populate_template(unit, reviews)
        self.template_value['can_request_new_review'] = False

        self.render('review_dashboard.html')


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
