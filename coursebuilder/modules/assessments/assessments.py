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

"""Module to manage assessments"""

__author__ = 'John Orr (jorr@google.com)'

import datetime
import logging
import os
import urllib

import appengine_config
from controllers import utils
from models import courses
from models import custom_modules
from models import models
from models import review as models_review
from models import student_work
from models import transforms
from models import utils as models_utils
from modules.courses import unit_outline
from modules.embed import embed
from modules.review import domain
from tools import verify

from google.appengine.ext import db

_BASE_DIR = os.path.join(appengine_config.BUNDLE_ROOT, 'modules', 'assessments')
_TEMPLATES_DIR = os.path.join(_BASE_DIR, 'templates')
_EMBEDDED_ASSESSMENT_KEY = 'assessment'

custom_module = None


def create_readonly_assessment_params(content, answers):
    """Creates parameters for a readonly assessment in the view templates."""
    assessment_params = {
        'preamble': content['assessment']['preamble'],
        'questionsList': content['assessment']['questionsList'],
        'answers': answers,
    }
    return assessment_params


class AssignmentsModuleMixin(object):
    def get_template(self, template_file, additional_dirs=None, prefs=None):
        return super(AssignmentsModuleMixin, self).get_template(
            template_file,
            additional_dirs=[_TEMPLATES_DIR] + (additional_dirs or []),
            prefs=prefs)


class AssessmentHandler(AssignmentsModuleMixin, utils.BaseHandler):
    """Handler for generating assessment page."""

    # pylint: disable=too-many-statements
    def get(self):
        """Handles GET requests."""
        embedded = bool(self.request.get('embedded'))

        student = None
        user = self.personalize_page_and_get_user()
        if user:
            student = models.Student.get_enrolled_student_by_user(user)
        student = student or models.TransientStudent()


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
        student_view = unit_outline.StudentCourseView(course, student)
        if not student_view.is_visible([self.unit_id]):
            self.redirect('/')
            return

        self.template_value['main_content'] = self.get_assessment_content(
            student, course, unit, as_lesson=False, embedded=embedded)
        self.template_value['assessment_name'] = assessment_name
        self.template_value['unit_id'] = self.unit_id
        self.template_value['navbar'] = {'course': True}
        if embedded:
            self.template_value['embed_child_js_url'] = embed.EMBED_CHILD_JS_URL
            self.template_value['gcb_html_element_class'] = 'hide-controls'

        self.render('assessment_page.html', save_location=not embedded)

    def get_assessment_content(
            self, student, course, unit, as_lesson, embedded=False):
        if embedded and course.needs_human_grader(unit):
            # I18N: This is an error message to an author of an online course.
            # The problem is that course assignments that are to be graded
            # by other students (peers) cannot be configured to be added
            # as content to external web pages. (I.e., some external site wants
            # to use this assignment as part of a page's content, but this
            # is not permitted)
            return self.app_context.gettext(
                'Peer-review assignments cannot be embedded in external pages.')

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

        self.template_value['embedded'] = embedded
        if self.request.get('onsubmit'):
            self.template_value['show_onsubmit_message'] = True
        self.template_value['unit_id'] = unit.unit_id
        self.template_value['now_available'] = course.is_unit_available(unit)
        self.template_value['transient_student'] = student.is_transient
        self.template_value['as_lesson'] = as_lesson
        self.template_value['assessment_title'] = unit.title
        self.template_value['assessment_xsrf_token'] = (
            utils.XsrfTokenManager.create_xsrf_token('assessment-post'))
        self.template_value['event_xsrf_token'] = (
            utils.XsrfTokenManager.create_xsrf_token('event-post'))

        self.template_value['grader'] = unit.workflow.get_grader()

        readonly_view = False
        due_date_exceeded = False
        submission_contents = None
        review_steps_for = []

        submission_due_date = unit.workflow.get_submission_due_date()
        if submission_due_date:
            self.template_value['submission_due_date'] = (
                submission_due_date.strftime(
                    utils.HUMAN_READABLE_DATETIME_FORMAT))

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
            if (models_review.ReviewUtils.has_completed_enough_reviews(
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

        if not course.needs_human_grader(unit):
            if not student.is_transient:
                submission = student_work.Submission.get(
                    unit.unit_id, student.get_key())
                if submission is not None:
                    submission_contents = transforms.loads(submission.contents)
                    if submission.updated_on is not None:
                        self.template_value['submission_date'] = (
                            submission.updated_on.strftime(
                                utils.HUMAN_READABLE_DATETIME_FORMAT))
                    if due_date_exceeded and unit.workflow.show_feedback():
                        score = submission_contents.get('rawScore', 0)
                        weight = submission_contents.get('totalWeight', 0)
                        percent = submission_contents.get('percentScore', 0)
                        self.template_value['show_feedback'] = True
                        self.template_value['score'] = '%d/%d (%d%%)' % (
                            score, weight, percent)

            if unit.workflow.is_single_submission() and submission is not None:
                readonly_view = True

            if readonly_view:
                configure_readonly_view(unit, submission_contents)

        if not readonly_view:
            if not student.is_transient:
                submission_contents = student_work.Submission.get_contents(
                    unit.unit_id, student.get_key())
            configure_active_view(unit, submission_contents)

        self.template_value['assessment_attempted'] = bool(submission_contents)

        return self.render_template_to_html(
            self.template_value, 'assessment.html')

    def configure_readonly_view_1_4(self, unit, submission_contents):
        self.template_value['readonly_student_assessment'] = (
            create_readonly_assessment_params(
                self.get_course().get_assessment_content(unit),
                student_work. StudentWorkUtils.get_answer_list(
                    submission_contents)))

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
                student_work.StudentWorkUtils.get_answer_list(
                    submission_contents))

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
            student_work.StudentWorkUtils.get_answer_list(review))

    def get_review_received_1_5(self, unit, review):
        return {
            'content': unit.html_review_form,
            'saved_answers': transforms.dumps(review)
        }


def store_score(course, student, assessment_type, score):
    """Stores a student's score on a particular assessment.

    Args:
        course: the course containing the assessment.
        student: the student whose data is stored.
        assessment_type: the type of the assessment.
        score: the student's score on this assessment.

    Returns:
        the result of the assessment, if appropriate.
    """
    # FIXME: Course creators can edit this code to implement custom
    # assessment scoring and storage behavior
    # TODO(pgbovine): Note that the latest version of answers are always saved,
    # but scores are only saved if they're higher than the previous attempt.
    # This can lead to unexpected analytics behavior. Resolve this.
    existing_score = course.get_score(student, assessment_type)
    # remember to cast to int for comparison
    if (existing_score is None) or (score > int(existing_score)):
        models_utils.set_score(student, assessment_type, score)


class AnswerHandler(AssignmentsModuleMixin, utils.BaseHandler):
    """Handler for saving assessment answers."""

    # Find student entity and save answers
    @db.transactional(xg=True)
    def update_assessment_transaction(
        self, key_name, assessment_type, new_answers, score):
        """Stores answer and updates user scores.

        Args:
            email: the student's email address.
            assessment_type: the title of the assessment.
            new_answers: the latest set of answers supplied by the student.
            score: the numerical assessment score.

        Returns:
            the student instance.
        """
        student = models.Student.get_by_key_name(key_name)
        if not student or not student.is_enrolled:
            raise Exception(
                'Expected enrolled student with key_name "%s".', key_name)

        course = self.get_course()

        # It may be that old Student entities don't have user_id set; fix it.
        if not student.user_id:
            student.user_id = self.get_user().user_id()

        answers = models.StudentAnswersEntity.get_by_key_name(student.user_id)
        if not answers:
            answers = models.StudentAnswersEntity(key_name=student.user_id)
        answers.updated_on = datetime.datetime.now()

        models_utils.set_answer(answers, assessment_type, new_answers)

        store_score(course, student, assessment_type, score)

        student.put()
        answers.put()

        # Also record the event, which is useful for tracking multiple
        # submissions and history.
        models.EventEntity.record(
            'submit-assessment', self.get_user(), transforms.dumps({
                'type': 'assessment-%s' % assessment_type,
                'values': new_answers, 'location': 'AnswerHandler'}))

        return student

    def get(self):
        """Handles GET requests.

        This method is here because if a student logs out when on the
        reviewed_assessment_confirmation page, that student is redirected to
        the GET method of the corresponding handler. It might be a good idea to
        merge this class with lessons.AssessmentHandler, which currently only
        has a GET handler.
        """
        self.redirect('/course')

    # pylint: disable=too-many-statements
    def post(self):
        """Handles POST requests."""
        embedded = bool(self.request.get('embedded'))

        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not self.assert_xsrf_token_or_fail(self.request, 'assessment-post'):
            return

        course = self.get_course()
        assessment_type = self.request.get('assessment_type')
        if not assessment_type:
            self.error(404)
            logging.error('No assessment type supplied.')
            return

        unit = course.find_unit_by_id(assessment_type)
        if unit is None or unit.type != verify.UNIT_TYPE_ASSESSMENT:
            self.error(404)
            logging.error('No assessment named %s exists.', assessment_type)
            return

        self.template_value['navbar'] = {'course': True}
        self.template_value['assessment'] = assessment_type
        self.template_value['assessment_name'] = unit.title
        self.template_value['is_last_assessment'] = (
            course.is_last_assessment(unit))
        self.template_value['unit_id'] = unit.unit_id

        # Convert answers from JSON to dict.
        answers = self.request.get('answers')
        answers = transforms.loads(answers) if answers else []

        grader = unit.workflow.get_grader()

        # Scores are not recorded for peer-reviewed assignments.
        score = 0
        if grader == courses.AUTO_GRADER:
            score = int(round(float(self.request.get('score'))))

        # Record assessment transaction.
        student = self.update_assessment_transaction(
            student.key().name(), assessment_type, answers, score)

        if grader == courses.HUMAN_GRADER:
            rp = course.get_reviews_processor()

            # Guard against duplicate submissions of a human-graded assessment.
            previously_submitted = rp.does_submission_exist(
                unit.unit_id, student.get_key())

            if not previously_submitted:
                # Check that the submission due date has not passed.
                time_now = datetime.datetime.now()
                submission_due_date = unit.workflow.get_submission_due_date()
                if submission_due_date and time_now > submission_due_date:
                    self.template_value['time_now'] = time_now.strftime(
                        utils.HUMAN_READABLE_DATETIME_FORMAT)
                    self.template_value['submission_due_date'] = (
                        submission_due_date.strftime(
                            utils.HUMAN_READABLE_DATETIME_FORMAT))
                    self.template_value['error_code'] = (
                        'assignment_deadline_exceeded')
                    self.render('error.html')
                    return

                submission_key = student_work.Submission.write(
                    unit.unit_id, student.get_key(), answers)
                rp.start_review_process_for(
                    unit.unit_id, submission_key, student.get_key())
                # Record completion event in progress tracker.
                course.get_progress_tracker().put_assessment_completed(
                    student, assessment_type)

            self.template_value['previously_submitted'] = previously_submitted

            matcher = unit.workflow.get_matcher()
            self.template_value['matcher'] = matcher
            if matcher == models_review.PEER_MATCHER:
                self.template_value['review_dashboard_url'] = (
                    'reviewdashboard?unit=%s' % unit.unit_id
                )

            self.render('reviewed_assessment_confirmation.html')
            return
        else:
            # Record completion event in progress tracker.
            course.get_progress_tracker().put_assessment_completed(
                student, assessment_type)

            # Save the submission in the datastore, overwriting the earlier
            # version if it exists.
            submission_key = student_work.Submission.write(
                unit.unit_id, student.get_key(), answers)
            course.update_final_grades(student)

            parent_unit = course.get_parent_unit(unit.unit_id)
            if parent_unit:
                next_url = '/unit?unit=%d&assessment=%d&confirmation' % (
                    parent_unit.unit_id, unit.unit_id)
                self.redirect(next_url)
            else:
                if embedded:
                    self.redirect('/%s?%s' %(
                        'assessment',
                        urllib.urlencode({
                            'embedded': 'true',
                            'onsubmit': 'true',
                            'name': unit.unit_id})))
                    return

                self.template_value['result'] = course.get_overall_result(
                    student)
                self.template_value['score'] = score
                self.template_value['overall_score'] = course.get_overall_score(
                    student)
                self.render('test_confirmation.html')


class AssessmentEmbed(embed.AbstractEmbed):
    ENROLLMENT_POLICY = embed.AutomaticEnrollmentPolicy

    @classmethod
    def get_redirect_url(cls, handler, target_slug=None):
        assessment_id = handler.request.path.split('/')[-1]
        return str('%s/%s?%s' % (
            cls.get_slug(handler, target_slug=target_slug),
            'assessment',
            urllib.urlencode({
                'name': assessment_id,
                'embedded': 'true'})))


def notify_module_enabled():
    embed.Registry.bind(_EMBEDDED_ASSESSMENT_KEY, AssessmentEmbed)


def register_module():

    namespaced_routes = [
        ('/answer', AnswerHandler),
        ('/assessment', AssessmentHandler),]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        'Assessment module',
        'Provide functionality for student assessment',
        [],
        namespaced_routes,
        notify_module_enabled=notify_module_enabled)

    return custom_module
