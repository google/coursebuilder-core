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
and also the logic used to determine when it has been earned by a student.
The qualification logic can be customized by:
  * using the designated user interface in course settings
  * editing the course.yaml file
  * adding Python code to custom_criteria.py

The appearance of the certificate can be customized either system-wide, or else
on a course-by-course basis. To customize the certificate appearance
system-wide, edit the file templates/certificate.html in this module.

To make a course-specific certificate, upload a file named "certificate.html"
into the View Templates section of the Dashboard > Assets tab. Images and
resources used by this file should also be uploaded in Dashboard > Assets.
"""

__author__ = [
    'Saifu Angto (saifu@google.com)',
    'John Orr (jorr@google.com)']


import gettext
import os

import appengine_config
from common import safe_dom
from common import schema_fields
from common import tags
from controllers import utils
from models import courses
from models import custom_modules
from modules.certificate import custom_criteria
from modules.dashboard import course_settings

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
        self.response.out.write(template.render({
            'student': student,
            'course': courses.Course.get_environ(
                self.app_context)['course']['title']
        }))


def _get_score_by_id(score_list, assessment_id):
    for score in score_list:
        if score['id'] == str(assessment_id):
            return score
    return None


def _prepare_custom_criterion(custom, student, course):
    assert hasattr(custom_criteria, custom), ((
        'custom criterion %s is not implemented '
        'as a function in custom_criteria.py.') % custom)
    assert (custom in custom_criteria.registration_table), ((
        'Custom criterion %s is not whitelisted '
        'in the registration_table in custom_criteria.py.') % custom)

    def _check_custom_criterion():
        if not getattr(custom_criteria, custom)(student, course):
            return False
        return True

    return _check_custom_criterion


def _prepare_assessment_criterion(score_list, criterion):
    score = _get_score_by_id(score_list, criterion['assessment_id'])
    assert score is not None, (
        'Invalid assessment id %s.' % criterion['assessment_id'])
    pass_percent = criterion.get('pass_percent', '')
    if pass_percent is not '':
        # Must be machine graded
        assert not score['human_graded'], (
            'If pass_percent is provided, '
            'the assessment must be machine graded.')
        pass_percent = float(pass_percent)
        assert (pass_percent >= 0.0) and (pass_percent <= 100.0), (
            'pass_percent must be between 0 and 100.')
    else:
        # Must be peer graded
        assert score['human_graded'], (
            'If pass_percent is not provided, '
            'the assessment must be human graded.')

    def _check_assessment_criterion():
        if not score['completed']:
            return False
        if pass_percent is not '':
            return score['score'] >= pass_percent
        return True

    return _check_assessment_criterion


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

    criteria_functions = []
    # First validate the correctness of _all_ provided criteria
    for criterion in environ['certificate_criteria']:
        assessment_id = criterion.get('assessment_id', '')
        custom = criterion.get('custom_criteria', '')
        assert (assessment_id is not '') or (custom is not ''), (
            'assessment_id and custom_criteria cannot be both empty.')
        if custom is not '':
            criteria_functions.append(
                _prepare_custom_criterion(custom, student, course))
        elif assessment_id is not '':
            criteria_functions.append(
                _prepare_assessment_criterion(score_list, criterion))
        else:
            assert False, 'Invalid certificate criterion %s.' % criterion

    # All criteria are valid, now do the checking.
    for criterion_function in criteria_functions:
        if not criterion_function():
            return False

    return True


def get_certificate_table_entry(unused_handler, student, course):
    # I18N: Title of section on page showing certificates for course completion.
    title = gettext.gettext('Certificate')

    if student_is_qualified(student, course):
        link = safe_dom.A(
            CERTIFICATE_HANDLER_PATH
        ).add_text(
            # I18N: Label on control to navigate to page showing certificate.
            gettext.gettext('Click for certificate'))
        return (title, link)
    else:
        return (
            title,
            # I18N: Text indicating student has not yet completed a course.
            gettext.gettext(
                'You have not yet met the course requirements for a '
                'certificate of completion.'))


def get_criteria_editor_schema(course):
    criterion_type = schema_fields.FieldRegistry(
        'Criterion',
        extra_schema_dict_values={'className': 'settings-list-item'})

    select_data = [('default', '-- Select requirement --'), (
        '', '-- Custom criterion --')]
    for unit in course.get_assessment_list():
        select_data.append((unit.unit_id, unit.title + (
            ' [Peer Graded]' if course.needs_human_grader(unit) else '')))

    criterion_type.add_property(schema_fields.SchemaField(
        'assessment_id', 'Requirement', 'string', optional=True,
        # The JS will only reveal the following description
        # for peer-graded assessments
        description='When specifying a peer graded assessment as criterion, '
            'the student should complete both the assessment '
            'and the minimum of peer reviews.',
        select_data=select_data,
        extra_schema_dict_values={
            'className': 'assessment-dropdown'}))

    criterion_type.add_property(schema_fields.SchemaField(
        'pass_percent', 'Passing Percentage', 'string', optional=True,
        extra_schema_dict_values={
            'className': 'pass-percent'}))

    select_data = [('', '-- Select criterion method--')] + [(
        x, x) for x in custom_criteria.registration_table]
    criterion_type.add_property(schema_fields.SchemaField(
        'custom_criteria', 'Custom Criterion', 'string', optional=True,
        select_data=select_data,
        extra_schema_dict_values={
            'className': 'custom-criteria'}))

    is_peer_assessment_table = {}
    for unit in course.get_assessment_list():
        is_peer_assessment_table[unit.unit_id] = (
            True if course.needs_human_grader(unit) else False)

    return schema_fields.FieldArray(
        'certificate_criteria', 'Certificate criteria',
        item_type=criterion_type,
        description='Certificate award criteria. Add the criteria which '
            'students must meet to be awarded a certificate of completion. '
            'In order to receive a certificate, '
            'the student must meet all the criteria.',
        extra_schema_dict_values={
            'is_peer_assessment_table': is_peer_assessment_table,
            'className': 'settings-list',
            'listAddLabel': 'Add a criterion',
            'listRemoveLabel': 'Delete criterion'})


custom_module = None


def register_module():
    """Registers this module in the registry."""

    def on_module_enabled():
        course_settings.CourseSettingsRESTHandler.REQUIRED_MODULES.append(
            'inputex-list')
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            courses.Course.SCHEMA_SECTION_COURSE].append(
                get_criteria_editor_schema)
        course_settings.CourseSettingsHandler.ADDITIONAL_DIRS.append(
            os.path.dirname(__file__))
        course_settings.CourseSettingsHandler.EXTRA_CSS_FILES.append(
            'course_settings.css')
        course_settings.CourseSettingsHandler.EXTRA_JS_FILES.append(
            'course_settings.js')
        utils.StudentProfileHandler.EXTRA_STUDENT_DATA_PROVIDERS.append(
            get_certificate_table_entry)

    def on_module_disabled():
        course_settings.CourseSettingsRESTHandler.REQUIRED_MODULES.remove(
            'inputex-list')
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[
            courses.Course.SCHEMA_SECTION_COURSE].remove(
                get_criteria_editor_schema)
        course_settings.CourseSettingsHandler.ADDITIONAL_DIRS.remove(
            os.path.dirname(__file__))
        course_settings.CourseSettingsHandler.EXTRA_CSS_FILES.remove(
            'course_settings.css')
        course_settings.CourseSettingsHandler.EXTRA_JS_FILES.remove(
            'course_settings.js')
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
