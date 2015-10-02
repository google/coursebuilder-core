# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Classes for management of individual students' peer review assignments."""

__author__ = 'Sean Lip (sll@google.com)'

import os
import urllib

from models import courses
from models import models
from models import review
from models import roles
from models import student_work
from models import transforms
from modules.assessments.assessments import create_readonly_assessment_params
from modules.review import domain


class AssignmentsRights(object):
    """Manages view/edit rights for assignments and reviews."""

    @classmethod
    def can_view(cls, handler):
        return roles.Roles.is_course_admin(handler.app_context)

    @classmethod
    def can_edit(cls, handler):
        return roles.Roles.is_course_admin(handler.app_context)

    @classmethod
    def can_delete(cls, handler):
        return cls.can_edit(handler)

    @classmethod
    def can_add(cls, handler):
        return cls.can_edit(handler)


def _get_assignment_html(
    handler, peer_reviewed_units, unit_id=None, reviewee_id=None,
    error_msg=None, readonly_assessment=None, review_steps=None,
    reviewers=None, reviews_params=None, model_version=None):
    """Renders a template allowing an admin to select an assignment."""
    edit_url = handler.canonicalize_url('/dashboard')

    return handler.render_template_to_html({
        'REVIEW_STATE_COMPLETED': domain.REVIEW_STATE_COMPLETED,
        'add_reviewer_action': handler.get_action_url('add_reviewer'),
        'add_reviewer_xsrf_token': handler.create_xsrf_token('add_reviewer'),
        'delete_reviewer_action': handler.get_action_url('delete_reviewer'),
        'delete_reviewer_xsrf_token': handler.create_xsrf_token(
            'delete_reviewer'),
        'edit_assignment_action': 'edit_assignment',
        'edit_url': edit_url,
        'error_msg': error_msg,
        'peer_reviewed_units': peer_reviewed_units,
        'readonly_student_assessment': readonly_assessment,
        'reviewee_id': reviewee_id or '',
        'reviewers': reviewers,
        'reviews_params': reviews_params,
        'review_steps': review_steps,
        'unit_id': unit_id,
        'model_version': model_version
        }, 'assignments_menu.html', [os.path.dirname(__file__)])


def _parse_request(course, unit_id, reviewee_id, reviewer_id=None):
    """Parses request parameters in a GET or POST request.

    Args:
      course: Course. A course object.
      unit_id: str. The id of the unit.
      reviewee_id: str. The email address of the reviewee.
      reviewer_id: str. The email address of the reviewer.

    Returns:
      - a dict containing some subset of the following keys: unit,
        reviewee, reviewer.
      - if necessary, an error message to be passed to the frontend.
    """
    request_params = {}

    # Check unit validity.
    if not unit_id:
        return request_params, ''

    unit = course.find_unit_by_id(unit_id)
    if not unit:
        return request_params, '404: Unit not found.'
    if (unit.workflow.get_grader() != courses.HUMAN_GRADER or
        unit.workflow.get_matcher() != review.PEER_MATCHER):
        return request_params, '412: This unit is not peer-graded.'
    request_params['unit'] = unit

    # Check reviewee validity.
    if not reviewee_id:
        return request_params, '412: No student email supplied.'

    reviewee, unique = models.Student.get_first_by_email(reviewee_id)
    if reviewee and not unique:
        return (request_params,
                'Several students with this email address exist.')
    if not reviewee or not reviewee.is_enrolled:
        return (request_params,
                'No student with this email address exists.')
    request_params['reviewee'] = reviewee

    # Check reviewer validity, if applicable.
    if reviewer_id is not None:
        if not reviewer_id:
            return request_params, '412: No reviewer email supplied.'
        reviewer, unique = models.Student.get_first_by_email(reviewer_id)
        if reviewer and not unique:
            return (request_params,
                    '412: Several students with this email address exist.')
        if not reviewer or not reviewer.is_enrolled:
            return (request_params,
                    '412: No reviewer with this email address exists.')
        request_params['reviewer'] = reviewer

    return request_params, ''


def get_edit_assignment(handler):
    """Shows interface for selecting and viewing a student assignment."""
    if not AssignmentsRights.can_view(handler):
        handler.error(401)
        return

    course = courses.Course(handler)
    peer_reviewed_units = course.get_peer_reviewed_units()

    page_title = 'Peer review'

    template_values = {}
    template_values['page_title'] = handler.format_title(page_title)

    unit_id = handler.request.get('unit_id')
    if not unit_id:
        # No unit has been set yet, so display an empty form.
        template_values['main_content'] = _get_assignment_html(
            handler, peer_reviewed_units)
        handler.render_page(template_values)
        return

    reviewee_id = handler.request.get('reviewee_id')
    # This field may be populated due to a redirect from a POST method.
    post_error_msg = handler.request.get('post_error_msg')

    request_params, error_msg = _parse_request(course, unit_id, reviewee_id)
    unit = request_params.get('unit')
    reviewee = request_params.get('reviewee')

    if error_msg:
        template_values['main_content'] = _get_assignment_html(
            handler, peer_reviewed_units, unit_id=unit_id,
            reviewee_id=reviewee_id, error_msg=error_msg)
        handler.render_page(template_values)
        return

    model_version = course.get_assessment_model_version(unit)
    assert model_version in courses.SUPPORTED_ASSESSMENT_MODEL_VERSIONS

    if model_version == courses.ASSESSMENT_MODEL_VERSION_1_4:
        get_readonly_assessment = _get_readonly_assessment_1_4
        get_readonly_review = _get_readonly_review_1_4
    elif model_version == courses.ASSESSMENT_MODEL_VERSION_1_5:
        get_readonly_assessment = _get_readonly_assessment_1_5
        get_readonly_review = _get_readonly_review_1_5
    else:
        raise ValueError('Bad assessment model version: %s' % model_version)

    # Render content.

    rp = course.get_reviews_processor()

    submission_and_review_steps = rp.get_submission_and_review_steps(
        unit.unit_id, reviewee.get_key())
    if not submission_and_review_steps:
        template_values['main_content'] = _get_assignment_html(
            handler, peer_reviewed_units, unit_id=unit_id,
            reviewee_id=reviewee_id,
            error_msg='412: This student hasn\'t submitted the assignment.'
        )
        handler.render_page(template_values)
        return

    readonly_assessment = get_readonly_assessment(
        handler, unit, submission_and_review_steps[0])

    review_steps = submission_and_review_steps[1]
    reviews = rp.get_reviews_by_keys(
        unit.unit_id,
        [review_step.review_key for review_step in review_steps],
        handle_empty_keys=True)

    reviews_params = []
    reviewers = []
    for idx, review_step in enumerate(review_steps):
        params = get_readonly_review(handler, unit, reviews[idx])
        reviews_params.append(params)

        reviewer = models.Student.get_by_user_id(
            review_step.reviewer_key.name()).email
        reviewers.append(reviewer)

    assert len(reviewers) == len(review_steps)
    assert len(reviews_params) == len(review_steps)

    template_values['main_content'] = _get_assignment_html(
        handler, peer_reviewed_units, unit_id=unit_id,
        reviewee_id=reviewee_id, readonly_assessment=readonly_assessment,
        review_steps=review_steps, error_msg=post_error_msg,
        reviewers=reviewers, reviews_params=reviews_params,
        model_version=model_version)
    handler.render_page(template_values)


def _get_readonly_assessment_1_4(handler, unit, submission_content):
    return create_readonly_assessment_params(
        courses.Course(handler).get_assessment_content(unit),
        student_work.StudentWorkUtils.get_answer_list(submission_content))


def _get_readonly_assessment_1_5(handler, unit, submission_content):
    return {
        'content': unit.html_content,
        'saved_answers': transforms.dumps(submission_content)
    }


def _get_readonly_review_1_4(handler, unit, review_content):
    return create_readonly_assessment_params(
        courses.Course(handler).get_review_content(unit),
        student_work.StudentWorkUtils.get_answer_list(review_content))


def _get_readonly_review_1_5(handler, unit, review_content):
    return {
        'content': unit.html_review_form,
        'saved_answers': transforms.dumps(review_content)
    }


def post_add_reviewer(handler):
    """Adds a new reviewer to a peer-reviewed assignment."""
    if not AssignmentsRights.can_edit(handler):
        handler.error(401)
        return

    course = courses.Course(handler)

    unit_id = handler.request.get('unit_id')
    reviewee_id = handler.request.get('reviewee_id')
    reviewer_id = handler.request.get('reviewer_id')

    request_params, post_error_msg = _parse_request(
        course, unit_id, reviewee_id, reviewer_id=reviewer_id)

    redirect_params = {
        'action': 'edit_assignment',
        'reviewee_id': reviewee_id,
        'reviewer_id': reviewer_id,
        'unit_id': unit_id,
    }

    if post_error_msg:
        redirect_params['post_error_msg'] = post_error_msg
        handler.redirect('/dashboard?%s' % urllib.urlencode(redirect_params))
        return

    unit = request_params.get('unit')
    reviewee = request_params.get('reviewee')
    reviewer = request_params.get('reviewer')

    rp = course.get_reviews_processor()
    reviewee_key = reviewee.get_key()
    reviewer_key = reviewer.get_key()

    try:
        rp.add_reviewer(unit.unit_id, reviewee_key, reviewer_key)
    except domain.TransitionError:
        redirect_params['post_error_msg'] = (
            '412: The reviewer is already assigned to this submission.')

    handler.redirect('/dashboard?%s' % urllib.urlencode(redirect_params))

def post_delete_reviewer(handler):
    """Deletes a reviewer from a peer-reviewed assignment."""
    if not AssignmentsRights.can_edit(handler):
        handler.error(401)
        return

    course = courses.Course(handler)

    unit_id = handler.request.get('unit_id')
    reviewee_id = handler.request.get('reviewee_id')
    review_step_key = handler.request.get('key')

    request_params, post_error_msg = _parse_request(
        course, unit_id, reviewee_id)

    redirect_params = {
        'action': 'edit_assignment',
        'reviewee_id': reviewee_id,
        'unit_id': unit_id,
    }

    if post_error_msg:
        redirect_params['post_error_msg'] = post_error_msg
        handler.redirect('/dashboard?%s' %
                         urllib.urlencode(redirect_params))
        return

    rp = course.get_reviews_processor()
    unit = request_params.get('unit')

    rp.delete_reviewer(unit.unit_id, review_step_key)

    handler.redirect('/dashboard?%s' % urllib.urlencode(redirect_params))
