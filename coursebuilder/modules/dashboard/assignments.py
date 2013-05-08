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

from controllers.lessons import create_readonly_assessment_params
from controllers.utils import ApplicationHandler
import jinja2
from models import courses
from models import models
from models import roles
from models.review import ReviewUtils

import messages


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


class AssignmentManager(ApplicationHandler):
    """A view for managing human-reviewed assignments."""

    def get_assignment_html(
        self, peer_reviewed_units, unit_id=None, reviewee_id=None,
        error_msg=None, readonly_assessment=None, reviews=None):
        """Renders a template allowing an admin to select an assignment."""
        edit_url = self.canonicalize_url('/dashboard')

        return jinja2.utils.Markup(self.get_template(
            'assignments_menu.html', [os.path.dirname(__file__)]
        ).render({
            'action': 'edit_assignment',
            'edit_url': edit_url,
            'error_msg': error_msg,
            'peer_reviewed_units': peer_reviewed_units,
            'reviewee_id': reviewee_id or '',
            'readonly_student_assessment': readonly_assessment,
            'reviews': reviews,
            'reviews_xsrf_token': self.create_xsrf_token('edit_reviews'),
            'unit_id': unit_id,
        }))

    def get_edit_assignment(self):
        """Shows interface for selecting and viewing a student assignment."""
        course = courses.Course(self)
        peer_reviewed_units = course.get_peer_reviewed_units()

        template_values = {}
        template_values['page_title'] = self.format_title('Peer Review')
        template_values['page_description'] = (
            messages.ASSIGNMENTS_MENU_DESCRIPTION)

        unit_id = self.request.get('unit_id')
        reviewee_id = self.request.get('reviewee_id')

        if not AssignmentsRights.can_view(self):
            template_values['main_content'] = self.get_assignment_html(
                peer_reviewed_units, error_msg='401: Access denied.')
            self.render_page(template_values)
            return

        # Check unit validity.
        if not unit_id:
            # No unit has been set yet, so display an empty form.
            template_values['main_content'] = self.get_assignment_html(
                peer_reviewed_units)
            self.render_page(template_values)
            return

        unit = course.find_unit_by_id(unit_id)
        if not unit:
            template_values['main_content'] = self.get_assignment_html(
                peer_reviewed_units, error_msg='404: Unit not found.')
            self.render_page(template_values)
            return

        if (unit.workflow.get_grader() != courses.HUMAN_GRADER or
            unit.workflow.get_matcher() != courses.PEER_MATCHER):
            template_values['main_content'] = self.get_assignment_html(
                peer_reviewed_units,
                error_msg='412: This unit is not peer-graded.'
            )
            self.render_page(template_values)
            return

        # Check reviewee validity.
        if not reviewee_id:
            template_values['main_content'] = self.get_assignment_html(
                peer_reviewed_units, unit_id=unit_id,
                error_msg='412: No student email supplied.'
            )
            self.render_page(template_values)
            return

        reviewee = models.Student.get_enrolled_student_by_email(reviewee_id)

        if not reviewee:
            template_values['main_content'] = self.get_assignment_html(
                peer_reviewed_units, unit_id=unit_id, reviewee_id=reviewee_id,
                error_msg='412: No student with this email address exists.'
            )
            self.render_page(template_values)
            return

        # Render content.
        assessment_content = course.get_assessment_content(unit)
        student_work = course.get_reviews_processor().get_student_work(
            reviewee, unit)
        answer_list = ReviewUtils.get_answer_list(
            student_work['submission'])

        readonly_assessment = create_readonly_assessment_params(
            assessment_content, answer_list
        )

        reviewers = student_work.get('reviewers')
        review_content = course.get_review_form_content(unit)
        reviews = []
        for (reviewer, review) in reviewers.iteritems():
            review['reviewer'] = reviewer
            review['params'] = create_readonly_assessment_params(
                review_content, review['review']
            )
            reviews.append(review)

        template_values['main_content'] = self.get_assignment_html(
            peer_reviewed_units, unit_id=unit_id, reviewee_id=reviewee_id,
            readonly_assessment=readonly_assessment, reviews=reviews)
        self.render_page(template_values)
