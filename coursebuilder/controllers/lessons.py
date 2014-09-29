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

import copy
import datetime
import urllib
import urlparse

from utils import BaseHandler
from utils import BaseRESTHandler
from utils import CAN_PERSIST_ACTIVITY_EVENTS
from utils import CAN_PERSIST_PAGE_EVENTS
from utils import CAN_PERSIST_TAG_EVENTS
from utils import HUMAN_READABLE_DATETIME_FORMAT
from utils import TRANSIENT_STUDENT
from utils import XsrfTokenManager

from common import jinja_utils
from models import courses
from models import models
from models import student_work
from models import transforms
from models.counters import PerfCounter
from models.models import Student
from models.models import StudentProfileDAO
from models.review import ReviewUtils
from models.student_work import StudentWorkUtils
from modules import courses as courses_module
from modules.review import domain
from tools import verify

from google.appengine.ext import db

COURSE_EVENTS_RECEIVED = PerfCounter(
    'gcb-course-events-received',
    'A number of activity/assessment events received by the server.')

COURSE_EVENTS_RECORDED = PerfCounter(
    'gcb-course-events-recorded',
    'A number of activity/assessment events recorded in a datastore.')

UNIT_PAGE_TYPE = 'unit'
ACTIVITY_PAGE_TYPE = 'activity'
ASSESSMENT_PAGE_TYPE = 'assessment'
ASSESSMENT_CONFIRMATION_PAGE_TYPE = 'test_confirmation'

TAGS_THAT_TRIGGER_BLOCK_COMPLETION = ['attempt-activity']
TAGS_THAT_TRIGGER_COMPONENT_COMPLETION = ['tag-assessment']
TAGS_THAT_TRIGGER_HTML_COMPLETION = ['attempt-lesson']


def get_first_lesson(handler, unit_id):
    """Returns the first lesson in the unit."""
    lessons = handler.get_course().get_lessons(unit_id)
    return lessons[0] if lessons else None


def _get_selected_unit_or_first_unit(handler):
    # Finds unit requested or a first unit in the course.
    u = handler.request.get('unit')
    unit = handler.get_course().find_unit_by_id(u)
    if not unit:
        units = handler.get_course().get_units()
        for current_unit in units:
            if verify.UNIT_TYPE_UNIT == current_unit.type:
                unit = current_unit
                break
    return unit


def _get_selected_or_first_lesson(handler, unit):
    # Find lesson requested or a first lesson in the unit.
    l = handler.request.get('lesson')
    lesson = None
    if not l:
        lesson = get_first_lesson(handler, unit.unit_id)
    else:
        lesson = handler.get_course().find_lesson_by_id(unit, l)
    return lesson


def extract_unit_and_lesson(handler):
    """Loads unit and lesson specified in the request."""

    unit = _get_selected_unit_or_first_unit(handler)
    if not unit:
        return None, None
    return unit, _get_selected_or_first_lesson(handler, unit)


def extract_unit_and_lesson_or_assessment(handler):
    unit = _get_selected_unit_or_first_unit(handler)
    if not unit:
        return None, None, None

    lesson = None
    lesson_id = handler.request.get('lesson')
    if lesson_id:
        lesson = handler.get_course().find_lesson_by_id(unit, lesson_id)

    assessment = None
    assessment_id = handler.request.get('assessment')
    if assessment_id:
        assessment = handler.get_course().find_unit_by_id(assessment_id)

    if lesson or assessment:
        return unit, lesson, assessment

    if unit.pre_assessment:
        return unit, None, handler.get_course().find_unit_by_id(
            unit.pre_assessment)

    first_lesson = get_first_lesson(handler, unit.unit_id)
    if first_lesson:
        return unit, first_lesson, None

    if unit.post_assessment:
        return unit, None, handler.get_course().find_unit_by_id(
            unit.post_assessment)

    return unit, None, None


def get_unit_and_lesson_id_from_url(handler, url):
    """Extracts unit and lesson ids from a URL."""
    url_components = urlparse.urlparse(url)
    query_dict = urlparse.parse_qs(url_components.query)

    if 'unit' not in query_dict:
        return None, None

    unit_id = query_dict['unit'][0]

    lesson_id = None
    if 'lesson' in query_dict:
        lesson_id = query_dict['lesson'][0]
    else:
        lesson_id = get_first_lesson(handler, unit_id).lesson_id

    return unit_id, lesson_id


def create_readonly_assessment_params(content, answers):
    """Creates parameters for a readonly assessment in the view templates."""
    assessment_params = {
        'preamble': content['assessment']['preamble'],
        'questionsList': content['assessment']['questionsList'],
        'answers': answers,
    }
    return assessment_params


def filter_assessments_used_within_units(units):
    # Remove assessments that are to be treated as if they were in a unit.
    referenced_assessments = set()
    for unit in units:
        if unit.type == verify.UNIT_TYPE_UNIT:
            if unit.pre_assessment:
                referenced_assessments.add(unit.pre_assessment)
            if unit.post_assessment:
                referenced_assessments.add(unit.post_assessment)
    ret = []
    for unit in list(units):
        if unit.unit_id not in referenced_assessments:
            ret.append(unit)
    return ret


def augment_assessment_units(course, student):
    """Adds additional fields to assessment units."""
    rp = course.get_reviews_processor()

    for unit in course.get_units():
        if unit.type == 'A':
            if unit.needs_human_grader():
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


def is_progress_recorded(handler, student):
    if student.is_transient:
        return False
    if CAN_PERSIST_ACTIVITY_EVENTS:
        return True
    course = handler.get_course()
    units = handler.get_track_matching_student(student)
    for unit in units:
        if unit.manual_progress:
            return True
        for lesson in course.get_lessons(unit.unit_id):
            if lesson.manual_progress:
                return True
    return False


def add_course_outline_to_template(handler, student):
    """Adds course outline with all units, lessons, progress to the template."""
    _tracker = handler.get_progress_tracker()
    if student and not student.is_transient:
        augment_assessment_units(handler.get_course(), student)
        handler.template_value['course_progress'] = (
            _tracker.get_course_progress(student))

    _tuples = []
    units = handler.get_track_matching_student(student)
    units = filter_assessments_used_within_units(units)
    progress = _tracker.get_or_create_progress(
          student) if is_progress_recorded(handler, student) else None
    for _unit in units:
        _lessons = handler.get_lessons(_unit.unit_id)
        _lesson_progress = None
        if progress:
            _lesson_progress = _tracker.get_lesson_progress(
                student, _unit.unit_id, progress=progress)
        pre_assessment = None
        if _unit.pre_assessment:
            pre_assessment = handler.find_unit_by_id(_unit.pre_assessment)
        post_assessment = None
        if _unit.post_assessment:
            post_assessment = handler.find_unit_by_id(_unit.post_assessment)

        _tuple = (_unit, _lessons, _lesson_progress,
                  pre_assessment, post_assessment)
        _tuples.append(_tuple)

    handler.template_value['course_outline'] = _tuples
    handler.template_value['unit_progress'] = _tracker.get_unit_progress(
        student, progress=progress)


class CourseHandler(BaseHandler):
    """Handler for generating course page."""

    @classmethod
    def get_child_routes(cls):
        """Add child handlers for REST."""
        return [('/rest/events', EventsRESTHandler)]

    def get(self):
        """Handles GET requests."""
        models.MemcacheManager.begin_readonly()
        try:
            user = self.personalize_page_and_get_user()
            if user is None:
                student = TRANSIENT_STUDENT
            else:
                student = Student.get_enrolled_student_by_email(user.email())
                profile = StudentProfileDAO.get_profile_by_user_id(
                    user.user_id())
                self.template_value['has_global_profile'] = profile is not None
                if not student:
                    student = TRANSIENT_STUDENT

            if (student.is_transient and
                not self.app_context.get_environ()['course']['browsable']):
                self.redirect('/preview')
                return

            # If we are on this page due to visiting the course base URL
            # (and not base url plus "/course"), redirect registered students
            # to the last page they were looking at.
            last_location = self.get_redirect_location(student)
            if last_location:
                self.redirect(last_location)
                return

            tracker = self.get_progress_tracker()
            units = self.get_track_matching_student(student)
            units = filter_assessments_used_within_units(units)
            self.template_value['units'] = units
            self.template_value['show_registration_page'] = True

            if student and not student.is_transient:
                augment_assessment_units(self.get_course(), student)
                self.template_value['course_progress'] = (
                    tracker.get_course_progress(student))
            elif user:
                profile = StudentProfileDAO.get_profile_by_user_id(
                    user.user_id())
                additional_registration_fields = self.app_context.get_environ(
                    )['reg_form']['additional_registration_fields']
                if profile is not None and not additional_registration_fields:
                    self.template_value['show_registration_page'] = False
                    self.template_value['register_xsrf_token'] = (
                        XsrfTokenManager.create_xsrf_token('register-post'))

            self.template_value['transient_student'] = student.is_transient
            self.template_value['progress'] = tracker.get_unit_progress(student)
            course = self.app_context.get_environ()['course']
            self.template_value['video_exists'] = bool(
                'main_video' in course and
                'url' in course['main_video'] and
                course['main_video']['url'])
            self.template_value['image_exists'] = bool(
                'main_image' in course and
                'url' in course['main_image'] and
                course['main_image']['url'])

            self.template_value['is_progress_recorded'] = is_progress_recorded(
                self, student)
            self.template_value['navbar'] = {'course': True}
        finally:
            models.MemcacheManager.end_readonly()
        self.render('course.html')


class UnitHandler(BaseHandler):
    """Handler for generating unit page."""

    class UnitLeftNavElements(object):

        def __init__(self, course, unit):
            self._urls = []
            self._index_by_label = {}

            if unit.pre_assessment:
                self._index_by_label['assessment.%d' % unit.pre_assessment] = (
                    len(self._urls))
                self._urls.append('unit?unit=%s&assessment=%d' % (
                    unit.unit_id, unit.pre_assessment))

            for lesson in course.get_lessons(unit.unit_id):
                self._index_by_label['lesson.%s' % lesson.lesson_id] = (
                    len(self._urls))
                self._urls.append('unit?unit=%s&lesson=%s' % (
                    unit.unit_id, lesson.lesson_id))

                if lesson.activity and lesson.activity_listed:
                    self._index_by_label['activity.%s' % lesson.lesson_id] = (
                        len(self._urls))
                    self._urls.append('unit?unit=%s&lesson=%s&activity=true' % (
                        unit.unit_id, lesson.lesson_id))

            if unit.post_assessment:
                self._index_by_label['assessment.%d' % unit.post_assessment] = (
                    len(self._urls))
                self._urls.append('unit?unit=%s&assessment=%d' % (
                    unit.unit_id, unit.post_assessment))

        def get_url_by(self, item_type, item_id, offset):
            index = self._index_by_label['%s.%s' % (item_type, item_id)]
            index += offset
            if index >= 0 and index < len(self._urls):
                return self._urls[index]
            else:
                return None

    def get(self):
        """Handles GET requests."""
        models.MemcacheManager.begin_readonly()
        try:
            student = self.personalize_page_and_get_enrolled(
                supports_transient_student=True)
            if not student:
                return

            # Extract incoming args
            unit, lesson, assessment = extract_unit_and_lesson_or_assessment(
                self)
            unit_id = unit.unit_id

            # If the unit is not currently available, and the user does not have
            # the permission to see drafts, redirect to the main page.
            available_units = self.get_track_matching_student(student)
            if ((not unit.now_available or unit not in available_units) and
                not courses_module.courses.can_see_drafts(self.app_context)):
                self.redirect('/')
                return

            # Set template values for nav bar and page type.
            self.template_value['navbar'] = {'course': True}

            # Set template values for a unit and its lesson entities
            self.template_value['unit'] = unit
            self.template_value['unit_id'] = unit.unit_id

            # These attributes are needed in order to render questions (with
            # progress indicators) in the lesson body. They are used by the
            # custom component renderers in the assessment_tags module.
            self.student = student
            self.unit_id = unit_id

            add_course_outline_to_template(self, student)
            self.template_value['is_progress_recorded'] = is_progress_recorded(
                self, student)

            if (unit.show_contents_on_one_page and
                'confirmation' not in self.request.params):
                self._show_all_contents(student, unit)
            else:
                self._show_single_element(student, unit, lesson, assessment)

            self._set_gcb_html_element_class()
        finally:
            models.MemcacheManager.end_readonly()
        self.render('unit.html')

    def _set_gcb_html_element_class(self):
        """Select conditional CSS to hide parts of the unit page."""

        # TODO(jorr): Add an integration test for this once, LTI producer and
        # consumer code is completely checked in.

        gcb_html_element_class = []

        if self.request.get('hide-controls') == 'true':
            gcb_html_element_class.append('hide-controls')

        if self.request.get('hide-lesson-title') == 'true':
            gcb_html_element_class.append('hide-lesson-title')

        self.template_value['gcb_html_element_class'] = (
            ' '.join(gcb_html_element_class))

    def _apply_gcb_tags(self, text):
        return jinja_utils.get_gcb_tags_filter(self)(text)

    def _show_all_contents(self, student, unit):
        course = self.get_course()
        display_content = []
        left_nav_elements = UnitHandler.UnitLeftNavElements(
            self.get_course(), unit)

        if unit.unit_header:
            display_content.append(self._apply_gcb_tags(unit.unit_header))

        if unit.pre_assessment:
            display_content.append(self.get_assessment_display_content(
                student, unit, course.find_unit_by_id(unit.pre_assessment),
                left_nav_elements, {}))

        for lesson in course.get_lessons(unit.unit_id):
            self.lesson_id = lesson.lesson_id
            self.lesson_is_scored = lesson.scored
            template_values = copy.copy(self.template_value)
            self.set_lesson_content(student, unit, lesson, left_nav_elements,
                                    template_values)
            display_content.append(self.render_template_to_html(
                template_values, 'lesson_common.html'))
            del self.lesson_id
            del self.lesson_is_scored

        if unit.post_assessment:
            display_content.append(self.get_assessment_display_content(
                student, unit, course.find_unit_by_id(unit.post_assessment),
                left_nav_elements, {}))

        if unit.unit_footer:
            display_content.append(self._apply_gcb_tags(unit.unit_footer))

        self.template_value['display_content'] = display_content

    def _showing_first_element(self, unit, lesson, assessment, is_activity):
        """Whether the unit page is showing the first element of a Unit."""

        # If the unit has a pre-assessment, then that's the first element;
        # we are showing the first element iff we are showing that assessment.
        if unit.pre_assessment:
            return (assessment and
                    str(assessment.unit_id) == str(unit.pre_assessment))

        # If there is no pre-assessment, there may be lessons.  If there
        # are any lessons, then the first element is the first unit component.
        # Iff we are showing that lesson, we're on the first component.
        unit_lessons = self.get_course().get_lessons(unit.unit_id)
        if unit_lessons:
            if lesson and lesson.lesson_id == unit_lessons[0].lesson_id:
                # If the first lesson has an activity, then we are showing
                # the first element if we are showing the lesson, and not
                # the activity.
                return not is_activity
            return False

        # If there is no pre-assessment and no lessons, then the post-assessment
        # is the first element.  We are on the first element if we're showing
        # that assessment.
        if unit.post_assessment:
            return (assessment and
                    str(assessment.unit_id) == str(unit.post_assessment))

        # If unit has no pre-assessment, no lessons, and no post-assessment,
        # then we're both at the first and last item.
        if (not unit.pre_assessment and
            not unit.post_assessment and
            not unit_lessons):
                return True

        return False

    def _showing_last_element(self, unit, lesson, assessment, is_activity):
        """Whether the unit page is showing the last element of a Unit."""

        # If the unit has a post-assessment, then that's the last element;
        # we are showing the last element iff we are showing that assessment.
        if unit.post_assessment:
            return (assessment and
                    str(assessment.unit_id) == str(unit.post_assessment))

        # If there is no post-assessment, there may be lessons.  If there
        # are any lessons, then the last element is the last unit component.
        # Iff we are showing that lesson, we're on the last component.
        unit_lessons = self.get_course().get_lessons(unit.unit_id)
        if unit_lessons:
            if lesson and lesson.lesson_id == unit_lessons[-1].lesson_id:
                # If the lesson has an activity, and we're showing the
                # activity, that's last.
                return is_activity == lesson.has_activity
            return False

        # If there is no post-assessment and there are no lessons, then
        # the pre-assessment is the last item in the unit.  We are on the
        # last element if we're showing that assessment.
        if unit.pre_assessment:
            return (assessment and
                    str(assessment.unit_id) == str(unit.pre_assessment))

        # If unit has no pre-assessment, no lessons, and no post-assessment,
        # then we're both at the first and last item.
        if (not unit.pre_assessment and
            not unit.post_assessment and
            not unit_lessons):
                return True

        return False

    def _show_single_element(self, student, unit, lesson, assessment):
        # Add markup to page which depends on the kind of content.
        left_nav_elements = UnitHandler.UnitLeftNavElements(
            self.get_course(), unit)

        # need 'activity' to be True or False, and not the string 'true' or None
        # pylint: disable-msg=g-explicit-bool-comparison
        is_activity = (self.request.get('activity') != '' or
                       '/activity' in self.request.path)
        display_content = []
        if (unit.unit_header and
            self._showing_first_element(unit, lesson, assessment, is_activity)):
                display_content.append(self._apply_gcb_tags(unit.unit_header))
        if assessment:
            if 'confirmation' in self.request.params:
                self.set_confirmation_content(student, unit, assessment,
                                              left_nav_elements)
                self.template_value['assessment_name'] = (
                    self.template_value.get('assessment_name').lower())
                display_content.append(self.render_template_to_html(
                    self.template_value, 'test_confirmation_content.html'))
            else:
                display_content.append(self.get_assessment_display_content(
                    student, unit, assessment, left_nav_elements,
                    self.template_value))
        elif lesson:
            self.lesson_id = lesson.lesson_id
            self.lesson_is_scored = lesson.scored
            if is_activity:
                self.set_activity_content(student, unit, lesson,
                                          left_nav_elements)
            else:
                self.set_lesson_content(student, unit, lesson,
                                        left_nav_elements, self.template_value)
            display_content.append(self.render_template_to_html(
                    self.template_value, 'lesson_common.html'))
        if (unit.unit_footer and
            self._showing_last_element(unit, lesson, assessment, is_activity)):
                display_content.append(self._apply_gcb_tags(unit.unit_footer))
        self.template_value['display_content'] = display_content

    def get_assessment_display_content(self, student, unit, assessment,
                                       left_nav_elements, template_values):
        template_values['page_type'] = ASSESSMENT_PAGE_TYPE
        template_values['assessment'] = assessment
        template_values['back_button_url'] = left_nav_elements.get_url_by(
            'assessment', assessment.unit_id, -1)
        template_values['next_button_url'] = left_nav_elements.get_url_by(
            'assessment', assessment.unit_id, 1)

        assessment_handler = AssessmentHandler()
        assessment_handler.app_context = self.app_context
        assessment_handler.request = self.request
        return assessment_handler.get_assessment_content(
            student, self.get_course(), assessment, as_lesson=True)

    def set_confirmation_content(self, student, unit, assessment,
                                 left_nav_elements):
        course = self.get_course()
        self.template_value['page_type'] = ASSESSMENT_CONFIRMATION_PAGE_TYPE
        self.template_value['unit'] = unit
        self.template_value['assessment'] = assessment
        self.template_value['is_confirmation'] = True
        self.template_value['assessment_name'] = assessment.title
        self.template_value['score'] = (
            course.get_score(student, str(assessment.unit_id)))
        self.template_value['is_last_assessment'] = (
            course.is_last_assessment(assessment))
        self.template_value['overall_score'] = (
            course.get_overall_score(student))
        self.template_value['result'] = course.get_overall_result(student)
        self.template_value['back_button_url'] = left_nav_elements.get_url_by(
            'assessment', assessment.unit_id, 0)
        self.template_value['next_button_url'] = left_nav_elements.get_url_by(
            'assessment', assessment.unit_id, 1)

    def set_activity_content(self, student, unit, lesson, left_nav_elements):
        self.template_value['page_type'] = ACTIVITY_PAGE_TYPE
        self.template_value['lesson'] = lesson
        self.template_value['lesson_id'] = lesson.lesson_id
        self.template_value['back_button_url'] = left_nav_elements.get_url_by(
            'activity', lesson.lesson_id, -1)
        self.template_value['next_button_url'] = left_nav_elements.get_url_by(
            'activity', lesson.lesson_id, 1)
        self.template_value['activity'] = {
            'title': lesson.activity_title,
            'activity_script_src': (
                self.get_course().get_activity_filename(unit.unit_id,
                                                        lesson.lesson_id))}
        self.template_value['page_type'] = 'activity'
        self.template_value['title'] = lesson.activity_title

        if is_progress_recorded(self, student):
            # Mark this page as accessed. This is done after setting the
            # student progress template value, so that the mark only shows up
            # after the student visits the page for the first time.
            self.get_course().get_progress_tracker().put_activity_accessed(
                student, unit.unit_id, lesson.lesson_id)

    def set_lesson_content(self, student, unit, lesson, left_nav_elements,
                           template_values):
        template_values['page_type'] = UNIT_PAGE_TYPE
        template_values['lesson'] = lesson
        template_values['lesson_id'] = lesson.lesson_id
        template_values['back_button_url'] = left_nav_elements.get_url_by(
            'lesson', lesson.lesson_id, -1)
        template_values['next_button_url'] = left_nav_elements.get_url_by(
            'lesson', lesson.lesson_id, 1)
        template_values['page_type'] = 'unit'
        template_values['title'] = lesson.title

        if not lesson.manual_progress and is_progress_recorded(self, student):
            # Mark this page as accessed. This is done after setting the
            # student progress template value, so that the mark only shows up
            # after the student visits the page for the first time.
            self.get_course().get_progress_tracker().put_html_accessed(
                student, unit.unit_id, lesson.lesson_id)


class AssessmentHandler(BaseHandler):
    """Handler for generating assessment page."""

    # pylint: disable-msg=too-many-statements
    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled(
            supports_transient_student=True)
        if not student:
            return

        # Extract incoming args, binding to self if needed.
        assessment_name = self.request.get('name')
        self.unit_id = assessment_name
        course = self.get_course()
        unit = course.find_unit_by_id(self.unit_id)
        if not unit:
            self.error(404)
            return

        # If assessment is used as a pre/post within a unit, go see that view.
        parent_unit = course.get_parent_unit(self.unit_id)
        if parent_unit:
            self.redirect('/unit?unit=%s&assessment=%s' %
                          (parent_unit.unit_id, self.unit_id))
            return

        # If the assessment is not currently available, and the user does not
        # have the permission to see drafts redirect to the main page.
        if (not unit.now_available and
            not courses_module.courses.can_see_drafts(self.app_context)):
            self.redirect('/')
            return

        self.template_value['main_content'] = (
            self.get_assessment_content(student, course, unit, as_lesson=False))
        self.template_value['assessment_name'] = assessment_name
        self.template_value['unit_id'] = self.unit_id
        self.template_value['navbar'] = {'course': True}
        self.render('assessment_page.html')

    def get_assessment_content(self, student, course, unit, as_lesson):
        model_version = course.get_assessment_model_version(unit)
        assert model_version in courses.SUPPORTED_ASSESSMENT_MODEL_VERSIONS
        self.template_value['model_version'] = model_version

        if model_version == courses.ASSESSMENT_MODEL_VERSION_1_4:
            configure_readonly_view = self.configure_readonly_view_1_4
            configure_active_view = self.configure_active_view_1_4
            get_review_received = self.get_review_received_1_4
        elif model_version == courses.ASSESSMENT_MODEL_VERSION_1_5:
            configure_readonly_view = self.configure_readonly_view_1_5
            configure_active_view = self.configure_active_view_1_5
            get_review_received = self.get_review_received_1_5
        else:
            raise ValueError('Bad assessment model version: %s' % model_version)

        self.template_value['unit_id'] = unit.unit_id
        self.template_value['as_lesson'] = as_lesson
        self.template_value['assessment_title'] = unit.title
        self.template_value['assessment_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('assessment-post'))
        self.template_value['event_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('event-post'))

        self.template_value['grader'] = unit.workflow.get_grader()

        readonly_view = False
        due_date_exceeded = False
        submission_contents = None
        review_steps_for = []

        submission_due_date = unit.workflow.get_submission_due_date()
        if submission_due_date:
            self.template_value['submission_due_date'] = (
                submission_due_date.strftime(HUMAN_READABLE_DATETIME_FORMAT))

            time_now = datetime.datetime.now()
            if time_now > submission_due_date:
                readonly_view = True
                due_date_exceeded = True
                self.template_value['due_date_exceeded'] = True

        if course.needs_human_grader(unit) and not student.is_transient:
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

                if submission_and_review_steps:
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

                self.template_value['reviews_received'] = [get_review_received(
                    unit, review) for review in reviews_for_student]
            else:
                submission_contents = student_work.Submission.get_contents(
                    unit.unit_id, student.get_key())

            # Determine whether to show the assessment in readonly mode.
            if submission_contents or due_date_exceeded:
                readonly_view = True
                configure_readonly_view(unit, submission_contents)

        if not readonly_view:
            if not student.is_transient:
                submission_contents = student_work.Submission.get_contents(
                    unit.unit_id, student.get_key())
            configure_active_view(unit, submission_contents)

        return self.render_template_to_html(
            self.template_value, 'assessment.html')

    def configure_readonly_view_1_4(self, unit, submission_contents):
        self.template_value['readonly_student_assessment'] = (
            create_readonly_assessment_params(
                self.get_course().get_assessment_content(unit),
                StudentWorkUtils.get_answer_list(submission_contents)))

    def configure_readonly_view_1_5(self, unit, submission_contents):
        self.template_value['readonly_student_assessment'] = True
        self.template_value['html_content'] = unit.html_content
        self.template_value['html_saved_answers'] = transforms.dumps(
            submission_contents)

    def configure_active_view_1_4(self, unit, submission_contents):
        self.template_value['assessment_script_src'] = (
            self.get_course().get_assessment_filename(unit.unit_id))
        if submission_contents:
            # If a previous submission exists, reinstate it.
            self.template_value['saved_answers'] = transforms.dumps(
                StudentWorkUtils.get_answer_list(submission_contents))

    def configure_active_view_1_5(self, unit, submission_contents):
        self.template_value['html_content'] = unit.html_content
        self.template_value['html_check_answers'] = unit.html_check_answers
        if submission_contents:
            # If a previous submission exists, reinstate it.
            self.template_value['html_saved_answers'] = transforms.dumps(
                submission_contents)

    def get_review_received_1_4(self, unit, review):
        return create_readonly_assessment_params(
            self.get_course().get_review_content(unit),
            StudentWorkUtils.get_answer_list(review))

    def get_review_received_1_5(self, unit, review):
        return {
            'content': unit.html_review_form,
            'saved_answers': transforms.dumps(review)
        }


class ReviewDashboardHandler(BaseHandler):
    """Handler for generating the index of reviews that a student has to do."""

    def _populate_template(self, course, unit, review_steps):
        """Adds variables to the template for the review dashboard."""
        self.template_value['assessment_name'] = unit.title
        self.template_value['unit_id'] = unit.unit_id

        parent_unit = course.get_parent_unit(unit.unit_id)

        if parent_unit is not None:
            self.template_value['back_link'] = 'unit?unit=%s&assessment=%s' % (
                parent_unit.unit_id, unit.unit_id)
        else:
            self.template_value['back_link'] = (
                'assessment?name=%s' % unit.unit_id)

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

        self._populate_template(course, unit, review_steps)
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
            self._populate_template(course, unit, review_steps)
            self.render('review_dashboard.html')


class ReviewHandler(BaseHandler):
    """Handler for generating the submission page for individual reviews."""

    # pylint: disable-msg=too-many-statements
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

        model_version = course.get_assessment_model_version(unit)
        assert model_version in courses.SUPPORTED_ASSESSMENT_MODEL_VERSIONS
        self.template_value['model_version'] = model_version

        if model_version == courses.ASSESSMENT_MODEL_VERSION_1_4:
            configure_assessment_view = self.configure_assessment_view_1_4
            configure_readonly_review = self.configure_readonly_review_1_4
            configure_active_review = self.configure_active_review_1_4
        elif model_version == courses.ASSESSMENT_MODEL_VERSION_1_5:
            configure_assessment_view = self.configure_assessment_view_1_5
            configure_readonly_review = self.configure_readonly_review_1_5
            configure_active_review = self.configure_active_review_1_5
        else:
            raise ValueError('Bad assessment model version: %s' % model_version)

        self.template_value['navbar'] = {'course': True}
        self.template_value['unit_id'] = unit.unit_id
        self.template_value['key'] = review_step_key

        submission_key = review_step.submission_key
        submission_contents = student_work.Submission.get_contents_by_key(
            submission_key)

        configure_assessment_view(unit, submission_contents)

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
            configure_readonly_review(unit, rev)
        else:
            # Populate the review form,
            configure_active_review(unit, rev)

        self.template_value['assessment_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('review-post'))
        self.template_value['event_xsrf_token'] = (
            XsrfTokenManager.create_xsrf_token('event-post'))

        self.render('review.html')

    def configure_assessment_view_1_4(self, unit, submission_contents):
        readonly_student_assessment = create_readonly_assessment_params(
            self.get_course().get_assessment_content(unit),
            StudentWorkUtils.get_answer_list(submission_contents))
        self.template_value[
            'readonly_student_assessment'] = readonly_student_assessment

    def configure_assessment_view_1_5(self, unit, submission_contents):
        self.template_value['html_review_content'] = unit.html_content
        self.template_value['html_reviewee_answers'] = transforms.dumps(
            submission_contents)

    def configure_readonly_review_1_4(self, unit, review_contents):
        readonly_review_form = create_readonly_assessment_params(
            self.get_course().get_review_content(unit),
            StudentWorkUtils.get_answer_list(review_contents))
        self.template_value['readonly_review_form'] = readonly_review_form

    def configure_readonly_review_1_5(self, unit, review_contents):
        self.template_value['readonly_review_form'] = True
        self.template_value['html_review_form'] = unit.html_review_form
        self.template_value['html_review_answers'] = transforms.dumps(
            review_contents)

    def configure_active_review_1_4(self, unit, review_contents):
        self.template_value['assessment_script_src'] = (
            self.get_course().get_review_filename(unit.unit_id))
        saved_answers = (
            StudentWorkUtils.get_answer_list(review_contents)
            if review_contents else [])
        self.template_value['saved_answers'] = transforms.dumps(saved_answers)

    def configure_active_review_1_5(self, unit, review_contents):
        self.template_value['html_review_form'] = unit.html_review_form
        self.template_value['html_review_answers'] = transforms.dumps(
            review_contents)

    def post(self):
        """Handles POST requests, when a reviewer submits a review."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not self.assert_xsrf_token_or_fail(self.request, 'review-post'):
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
            course.update_final_grades(student)
        except domain.TransitionError:
            self.template_value['error_code'] = 'review_already_submitted'
            self.render('error.html')
            return

        self.render('review_confirmation.html')


class EventsRESTHandler(BaseRESTHandler):
    """Provides REST API for an Event."""

    def get(self):
        """Returns a 404 error; this handler should not be GET-accessible."""
        self.error(404)
        return

    def _add_location_facts(self, payload_json):
        payload_dict = transforms.loads(payload_json)
        if 'loc' not in payload_dict:
            payload_dict['loc'] = {}
        loc = payload_dict['loc']
        loc['locale'] = self.get_locale_for(self.request, self.app_context)
        loc['language'] = self.request.headers.get('Accept-Language')
        loc['country'] = self.request.headers.get('X-AppEngine-Country')
        loc['region'] = self.request.headers.get('X-AppEngine-Region')
        loc['city'] = self.request.headers.get('X-AppEngine-City')
        lat_long = self.request.headers.get('X-AppEngine-CityLatLong')
        if lat_long:
            latitude, longitude = lat_long.split(',')
            loc['lat'] = float(latitude)
            loc['long'] = float(longitude)
        payload_json = transforms.dumps(payload_dict).lstrip(
            models.transforms.JSON_XSSI_PREFIX)
        return payload_json

    def post(self):
        """Receives event and puts it into datastore."""

        COURSE_EVENTS_RECEIVED.inc()
        can = (
            CAN_PERSIST_ACTIVITY_EVENTS.value or
            CAN_PERSIST_PAGE_EVENTS.value or
            CAN_PERSIST_TAG_EVENTS.value)
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
        payload_json = self._add_location_facts(payload_json)
        models.EventEntity.record(source, user, payload_json)
        COURSE_EVENTS_RECORDED.inc()

        self.process_event(user, source, payload_json)

    def process_event(self, user, source, payload_json):
        """Processes an event after it has been recorded in the event stream."""

        student = models.Student.get_enrolled_student_by_email(user.email())
        if not student:
            return

        payload = transforms.loads(payload_json)

        if 'location' not in payload:
            return

        source_url = payload['location']

        if source in TAGS_THAT_TRIGGER_BLOCK_COMPLETION:
            unit_id, lesson_id = get_unit_and_lesson_id_from_url(
                self, source_url)
            if unit_id is not None and lesson_id is not None:
                self.get_course().get_progress_tracker().put_block_completed(
                    student, unit_id, lesson_id, payload['index'])
        elif source in TAGS_THAT_TRIGGER_COMPONENT_COMPLETION:
            unit_id, lesson_id = get_unit_and_lesson_id_from_url(
                self, source_url)
            cpt_id = payload['instanceid']
            if (unit_id is not None and lesson_id is not None and
                cpt_id is not None):
                self.get_course().get_progress_tracker(
                    ).put_component_completed(
                        student, unit_id, lesson_id, cpt_id)
        elif source in TAGS_THAT_TRIGGER_HTML_COMPLETION:
            # Records progress for scored lessons.
            unit_id, lesson_id = get_unit_and_lesson_id_from_url(
                self, source_url)
            course = self.get_course()
            unit = course.find_unit_by_id(unit_id)
            lesson = course.find_lesson_by_id(unit, lesson_id)
            if (unit_id is not None and
                lesson_id is not None and
                not lesson.manual_progress):
                self.get_course().get_progress_tracker().put_html_completed(
                    student, unit_id, lesson_id)
