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

"""Classes and methods to create and manage Certificates.

Course creators will need to customize both the appearance of the certificate,
and also the logic to used determine when it has been earned by a student. To
customize the qualification logic, edit the method
    ShowCertificateHandler.student_is_qualified
below.

The appearance of the certificate can be customized either system-wide, or else
on a course-by-course basis. To customize the certificate appearance
system-wide, edit the file templates/certificate.html in this module.

To make a course-specific certificate, upload a file named "certificate.html"
into the View Teplates section of the Dashboard > Assets tab. Images and
resources used by this file should also be uploaded in Dashboard > Assets.
"""

__author__ = [
    'Saifu Angto (saifu@google.com)',
    'John Orr (jorr@google.com)']


import gettext
import os

import appengine_config
from common import safe_dom
from common import tags
from controllers import utils
from models import custom_modules
from modules.certificate import custom_criteria

CERTIFICATE_HANDLER_PATH = 'certificate'
RESOURCES_PATH = '/modules/certificate/resources'


class ShowCertificateHandler(utils.BaseHandler):
    """Handler for student to print course certificate."""

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not student_is_qualified(student, self.get_course()):
            self.redirect('/')
            return

        templates_dir = os.path.join(
            appengine_config.BUNDLE_ROOT, 'modules', 'certificate', 'templates')
        template = self.get_template('certificate.html', [templates_dir])
        self.response.out.write(template.render({'student': student}))


def _get_score_by_id(score_list, assignment_id):
    for score in score_list:
        if score['id'] == str(assignment_id):
            return score
    return None


def _check_assignment_criterion(criterion, score_list):
    """Checks whether the criterion for an assessment is met."""

    score = _get_score_by_id(score_list, criterion['assignment_id'])
    if not score['completed']:
        return False
    if 'pass_percent' in criterion:
        return score['score'] >= criterion['pass_percent']
    else:
        return True


def student_is_qualified(student, course):
    """Determines whether the student has met criteria for a certificate.

    Args:
        student: models.models.Student. The student entity to test.
        course: modesl.courses.Course. The course which the student is
            enrolled in.

    Returns:
        True if the student is qualified, False otherwise.
    """

    environ = course.app_context.get_environ()
    score_list = course.get_all_scores(student)

    if not environ.get('certificate_criteria'):
        return False

    # First validate the correctness of _all_ provided criteria
    for criterion in environ['certificate_criteria']:
        if 'custom_criteria' in criterion:
            custom = criterion['custom_criteria']
            assert hasattr(custom_criteria, custom), (
                'custom criterion %s is not implemented' +
                'as a function in custom_criteria.py.' % custom)
            assert (custom in custom_criteria.registration_table), (
                'Custom criterion %s is not whitelisted ' +
                'in the registration_table in custom_criteria.py.' % custom)
        elif 'assignment_id' in criterion:
            score = _get_score_by_id(score_list, criterion['assignment_id'])
            assert score is not None, (
                'Invalid assessment id %s.' % criterion['assignment_id'])
            if 'pass_percent' in criterion:
                # Must be machine graded
                assert not score['human_graded'], (
                    'If pass_percent is provided, '
                    'the assessment must be machine graded.')
                assert (criterion['pass_percent'] >= 0) and (
                    criterion['pass_percent'] <= 100), (
                    'pass_percent must be between 0 and 100.')
            else:
                # Must be peer graded
                assert score['human_graded'], (
                    'If pass_percent is not provided, '
                    'the assessment must be human graded.')
        else:
            assert False, 'Invalid certificate criterion %s.' % criterion

    # All criteria are valid, now do the checking.
    for criterion in environ['certificate_criteria']:
        if 'custom_criteria' in criterion:
            if not getattr(custom_criteria, criterion['custom_criteria'])(
                    student, course):
                return False
        elif 'assignment_id' in criterion:
            if not _check_assignment_criterion(criterion, score_list):
                return False

    return True


def get_certificate_table_entry(student, course):
    title = gettext.gettext('Certificate')

    if student_is_qualified(student, course):
        link = safe_dom.A(
            CERTIFICATE_HANDLER_PATH
        ).add_text(
            gettext.gettext('Click for certificate'))
        return {title: link}
    else:
        return {title: gettext.gettext(
            'You have not yet met the course requirements for a certificate of '
            'completion.')}


custom_module = None


def register_module():
    """Registers this module in the registry."""

    def on_module_enabled():
        utils.StudentProfileHandler.EXTRA_STUDENT_DATA_PROVIDERS.append(
            get_certificate_table_entry)

    def on_module_disabled():
        utils.StudentProfileHandler.EXTRA_STUDENT_DATA_PROVIDERS.remove(
            get_certificate_table_entry)

    global_routes = [
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    namespaced_routes = [
        ('/' + CERTIFICATE_HANDLER_PATH, ShowCertificateHandler)]

    global custom_module
    custom_module = custom_modules.Module(
        'Show Certificate',
        'A page to show student certificate.',
        global_routes, namespaced_routes,
        notify_module_disabled=on_module_disabled,
        notify_module_enabled=on_module_enabled)
    return custom_module
