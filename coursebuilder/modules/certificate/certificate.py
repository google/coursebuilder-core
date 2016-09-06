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


import os
import StringIO

from mapreduce import context
from reportlab.lib import pagesizes
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

import appengine_config
from common import resource
from common import safe_dom
from common import schema_fields
from common import tags
from controllers import sites
from controllers import utils
from models import analytics
from models import courses
from models import custom_modules
from models import data_sources
from models import jobs
from models import models
from models import progress
from models import services
from modules.analytics import student_aggregate
from modules.certificate import custom_criteria
from modules.certificate import messages
from modules.courses import settings
from modules.dashboard import dashboard
from modules.news import news

MODULE_NAME = 'certificates'
MODULE_TITLE = 'Certificates'
CERTIFICATE_HANDLER_PATH = 'certificate'
CERTIFICATE_PDF_HANDLER_PATH = 'certificate.pdf'
RESOURCES_PATH = '/modules/certificate/resources'

# Not a fully-fledged resource key, but since the News module only needs
# something that walks like a resource key and quacks like a resource key,
# this is close enough: It parses like one, and the type does not collide
# with other resource type names.  It is also "unique enough", in that
# since it's per-student, we don't really care what the ID component of
# the key is.
RESOURCE_TYPE = 'certificate'
RESOURCE_KEY = RESOURCE_TYPE + resource.Key.SEPARATOR + '1'


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

        environ = self.app_context.get_environ()

        templates_dir = os.path.join(
            appengine_config.BUNDLE_ROOT, 'modules', 'certificate', 'templates')
        template = self.get_template('certificate.html', [templates_dir])
        self.response.out.write(template.render({
            'student': student,
            'course': environ['course']['title'],
            'google_analytics_id': environ['course'].get('google_analytics_id')
        }))


class ShowCertificatePdfHandler(utils.BaseHandler):
    """Handler for student to print course certificate."""

    def _print_cert(self, out, course, student):

        c = canvas.Canvas(out, pagesize=pagesizes.landscape(pagesizes.LETTER))
        c.setTitle('Course Builder Certificate')

        # Draw the background image
        image_path = os.path.join(
            appengine_config.BUNDLE_ROOT,
            'modules', 'certificate', 'resources', 'images', 'cert.png')
        image_data = open(image_path).read()
        image = canvas.ImageReader(StringIO.StringIO(image_data))
        c.drawImage(
            image, 0, -1.5 * inch, width=11 * inch, preserveAspectRatio=True)

        text = c.beginText()

        text.setTextOrigin(0.5 * inch, 4.5 * inch)
        text.setFont('Helvetica', 40)
        text.setFillColorRGB(75.0 / 255, 162.0 / 255, 65.0 / 255)
        # I18N: Message fragment on a certificate of course completion.
        # Title line indicating what this page is.
        text.textLine(self.gettext('Certificate of Completion'))

        text.setTextOrigin(0.5 * inch, 4.0 * inch)
        text.setFillColorRGB(0.4, 0.4, 0.4)
        text.setFont('Helvetica', 20)
        # I18N: Message fragment on a certificate of course completion.
        # On a separate line, preceding the name of the student.  Indicates
        # that the certificate is being presented to someone.
        text.textLine(self.gettext('Presented to'))

        text.setTextOrigin(0.5 * inch, 2.3 * inch)
        # I18N: Message fragment on a certificate of course completion.
        # Indicates that the student has successfully completed something.
        text.textLine(self.gettext('for successfully completing the'))
        # I18N: Message fragment on a certificate of course completion.
        # Gives the name of the course, followed by the word "course".
        text.textLine(self.gettext('%(course)s course') % {'course': course})

        c.drawText(text)

        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(0.1)
        c.line(0.5 * inch, 3.0 * inch, 10.5 * inch, 3.0 * inch)

        c.setFont('Helvetica', 24)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawCentredString(5.0 * inch, 3.1 * inch, student.name)

        c.showPage()
        c.save()

    def get(self):
        """Handles GET requests."""
        student = self.personalize_page_and_get_enrolled()
        if not student:
            return

        if not student_is_qualified(student, self.get_course()):
            self.redirect('/')
            return

        course = courses.Course.get_environ(self.app_context)['course']['title']

        self.response.headers['Content-Type'] = 'application/pdf'
        self.response.headers['Content-Disposition'] = (
            'attachment; filename=certificate.pdf')
        self._print_cert(self.response.out, course, student)


def _get_score_by_id(score_list, assessment_id):
    for score in score_list:
        if score['id'] == str(assessment_id):
            return score
    return None


def _prepare_custom_criterion(custom, student, course, explanations):
    assert hasattr(custom_criteria, custom), ((
        'custom criterion %s is not implemented '
        'as a function in custom_criteria.py.') % custom)
    assert (custom in custom_criteria.registration_table), ((
        'Custom criterion %s is not whitelisted '
        'in the registration_table in custom_criteria.py.') % custom)

    def _check_custom_criterion():
        criterion = getattr(custom_criteria, custom)
        if not criterion(student, course, explanations=explanations):
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


def student_is_qualified(student, course, explanations=None):
    """Determines whether the student has met criteria for a certificate.

    Args:
        student: models.models.Student. The student entity to test.
        course: modesl.courses.Course. The course which the student is
            enrolled in.
        explanations: list. Holder for a list of explanatory strings. Typically
            this will hold explanation of which criteria remain to be be met.

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
                _prepare_custom_criterion(
                    custom, student, course, explanations))
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


def get_certificate_table_entry(handler, student, course):
    # I18N: Title of section on page showing certificates for course completion.
    title = handler.gettext('Certificate')

    explanations = []
    if student_is_qualified(student, course, explanations=explanations):
        nl = safe_dom.NodeList()
        nl.append(
            safe_dom.A(
                CERTIFICATE_HANDLER_PATH
            ).add_text(
                # I18N: Label on control to navigate to page showing certificate
                handler.gettext('Click for certificate'))
        ).append(
            safe_dom.Text(' | ')
        ).append(
            safe_dom.A(
                CERTIFICATE_PDF_HANDLER_PATH
            ).add_text(
                # I18N: Link for a PDF.
                handler.gettext('Download PDF'))
        )
        return (title, nl)
    else:
        nl = safe_dom.NodeList()
        nl.append(
            safe_dom.Text(
                # I18N: Text indicating student has not yet completed a course.
                handler.gettext(
                    'You have not yet met the course requirements for a '
                    'certificate of completion.')))
        if explanations:
            ul = safe_dom.Element('ul', className='certificate-explanations')
            for expl in explanations:
                ul.append(safe_dom.Element('li').add_text(expl))
            nl.append(ul)
        return (title, nl)


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
        'assessment_id', 'Requirement', 'string',
        # The JS will only reveal the following description
        # for peer-graded assessments
        description='When specifying a peer graded assessment as criterion, '
            'the student should complete both the assessment '
            'and the minimum of peer reviews.',
        extra_schema_dict_values={
            'className': 'inputEx-Field assessment-dropdown'
        }, i18n=False, optional=True, select_data=select_data))

    criterion_type.add_property(schema_fields.SchemaField(
        'pass_percent', 'Passing Percentage', 'string',
        extra_schema_dict_values={
            'className': 'pass-percent'
        }, i18n=False, optional=True))

    select_data = [('', '-- Select criterion method--')] + [(
        x, x) for x in custom_criteria.registration_table]
    criterion_type.add_property(schema_fields.SchemaField(
        'custom_criteria', 'Custom Criterion', 'string',
        extra_schema_dict_values={
            'className': 'custom-criteria'
        }, i18n=False, optional=True, select_data=select_data))

    is_peer_assessment_table = {}
    for unit in course.get_assessment_list():
        is_peer_assessment_table[unit.unit_id] = (
            True if course.needs_human_grader(unit) else False)

    return schema_fields.FieldArray(
        'certificate_criteria', 'Certificate Criteria',
        item_type=criterion_type,
        description=services.help_urls.make_learn_more_message(
            messages.CERTIFICATE_CRITERIA_DESCRIPTION,
            'certificate:certificate_criteria'),
        extra_schema_dict_values={
            'is_peer_assessment_table': is_peer_assessment_table,
            'className': 'settings-list',
            'listAddLabel': 'Add a criterion',
            'listRemoveLabel': 'Delete criterion'},
        optional=True)


TOTAL_CERTIFICATES = 'total_certificates'
TOTAL_ACTIVE_STUDENTS = 'total_active_students'
TOTAL_STUDENTS = 'total_students'


class CertificatesEarnedGenerator(jobs.AbstractCountingMapReduceJob):

    @staticmethod
    def get_description():
        return 'certificates earned'

    def build_additional_mapper_params(self, app_context):
        return {'course_namespace': app_context.get_namespace_name()}

    @staticmethod
    def entity_class():
        return models.Student

    @staticmethod
    def map(student):
        params = context.get().mapreduce_spec.mapper.params
        ns = params['course_namespace']
        app_context = sites.get_course_index().get_app_context_for_namespace(ns)
        course = courses.Course(None, app_context=app_context)
        if student_is_qualified(student, course):
            yield(TOTAL_CERTIFICATES, 1)
        if student.scores:
            yield(TOTAL_ACTIVE_STUDENTS, 1)
        yield(TOTAL_STUDENTS, 1)


class CertificatesEarnedDataSource(data_sources.SynchronousQuery):

    @staticmethod
    def required_generators():
        return [CertificatesEarnedGenerator]

    @classmethod
    def get_name(cls):
        return 'certificates_earned'

    @classmethod
    def get_title(cls):
        return 'Certificates Earned'

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log,
                   unused_source_context):
        reg = schema_fields.FieldRegistry(
            'Certificates Earned',
            description='Scalar values aggregated over entire course giving '
            'counts of certificates earned/not-yet-earned.  Only one row will '
            'ever be returned from this data source.')
        reg.add_property(schema_fields.SchemaField(
            TOTAL_STUDENTS, 'Total Students', 'integer',
            description='Total number of students in course'))
        reg.add_property(schema_fields.SchemaField(
            TOTAL_CERTIFICATES, 'Total Certificates', 'integer',
            description='Total number of certificates earned'))
        reg.add_property(schema_fields.SchemaField(
            TOTAL_ACTIVE_STUDENTS, 'Total Active Students', 'integer',
            description='Number of "active" students.  These are students who '
            'have taken at least one assessment.  Note that it is not likely '
            'that a student has achieved a certificate without also being '
            'considered "active".'))
        return reg.get_json_schema_dict()['properties']

    @staticmethod
    def fill_values(app_context, template_values, certificates_earned_job):
        # Set defaults
        template_values.update({
            TOTAL_CERTIFICATES: 0,
            TOTAL_ACTIVE_STUDENTS: 0,
            TOTAL_STUDENTS: 0,
            })
        # Override with actual values from m/r job, if present.
        template_values.update(
            jobs.MapReduceJob.get_results(certificates_earned_job))


def register_analytic():
    data_sources.Registry.register(CertificatesEarnedDataSource)
    name = 'certificates_earned'
    title = 'Certificates'
    certificates_earned = analytics.Visualization(
        name, title, 'certificates_earned.html',
        data_source_classes=[CertificatesEarnedDataSource])
    dashboard.DashboardHandler.add_sub_nav_mapping(
        'analytics', name, title, action='analytics_certificates_earned',
        contents=analytics.TabRenderer([certificates_earned]))


class CertificateAggregator(
    student_aggregate.AbstractStudentAggregationComponent):

    @classmethod
    def get_name(cls):
        return 'certificate'

    @classmethod
    def get_event_sources_wanted(cls):
        return []

    @classmethod
    def build_static_params(cls, unused_app_context):
        return None

    @classmethod
    def process_event(cls, event, static_params):
        return None

    @classmethod
    def produce_aggregate(cls, course, student, unused_static_params,
                          unused_event_items):
        return {'earned_certificate': student_is_qualified(student, course)}

    @classmethod
    def get_schema(cls):
        return schema_fields.SchemaField(
          'earned_certificate', 'Earned Certificate', 'boolean',
          description='Whether the student has earned a course completion '
          'certificate based on the criteria in place when this fact was '
          'generated.')


def _post_update_progress(course, student, progress_, event_entity, event_key):
    """Called back when student has progress event recorded."""

    if student_is_qualified(student, course):
        item = news.NewsItem(RESOURCE_KEY, CERTIFICATE_HANDLER_PATH)
        news.StudentNewsDao.add_news_item(item, overwrite_existing=False)


def _get_i18n_news_title(_unused_key):
    app_context = sites.get_app_context_for_current_request()
    # I18N: Shown in list of news item titles (short descriptions)
    # when student has earned a course completion certificate.
    return app_context.gettext('Course completion certificate earned!')


custom_module = None


def register_module():
    """Registers this module in the registry."""

    def on_module_enabled():
        register_analytic()
        courses.Course.OPTIONS_SCHEMA_PROVIDERS[MODULE_NAME].append(
            get_criteria_editor_schema)
        courses.Course.OPTIONS_SCHEMA_PROVIDER_TITLES[
            MODULE_NAME] = MODULE_TITLE
        settings.CourseSettingsHandler.register_settings_section(MODULE_NAME)
        settings.CourseSettingsHandler.ADDITIONAL_DIRS.append(
            os.path.dirname(__file__))
        settings.CourseSettingsHandler.EXTRA_CSS_FILES.append(
            'course_settings.css')
        settings.CourseSettingsHandler.EXTRA_JS_FILES.append(
            'course_settings.js')
        utils.StudentProfileHandler.EXTRA_STUDENT_DATA_PROVIDERS.append(
            get_certificate_table_entry)
        student_aggregate.StudentAggregateComponentRegistry.register_component(
            CertificateAggregator)
        progress.UnitLessonCompletionTracker.POST_UPDATE_PROGRESS_HOOK.append(
            _post_update_progress)
        news.I18nTitleRegistry.register(RESOURCE_TYPE, _get_i18n_news_title)

    global_routes = [
        (os.path.join(RESOURCES_PATH, '.*'), tags.ResourcesHandler)]

    namespaced_routes = [
        ('/' + CERTIFICATE_HANDLER_PATH, ShowCertificateHandler),
        ('/' + CERTIFICATE_PDF_HANDLER_PATH, ShowCertificatePdfHandler)]

    global custom_module  # pylint: disable=global-statement
    custom_module = custom_modules.Module(
        MODULE_TITLE,
        'A page to show student certificate.',
        global_routes, namespaced_routes,
        notify_module_enabled=on_module_enabled)
    return custom_module
