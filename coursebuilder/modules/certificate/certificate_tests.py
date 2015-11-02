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

"""Tests for modules/certificate/."""

__author__ = 'John Orr (jorr@google.com)'


from controllers import sites
from models import courses
from models import models
from models import student_work
from modules.certificate import certificate
from modules.certificate import custom_criteria
from modules.review import domain
from modules.review import peer
from modules.review import review as review_module
from tests.functional import actions

from google.appengine.api import namespace_manager
from google.appengine.ext import db


class MockHandler(object):

    def gettext(self, text):
        return text


class CertificateHandlerTestCase(actions.TestBase):
    """Tests for the handler which presents the certificate."""

    def setUp(self):
        super(CertificateHandlerTestCase, self).setUp()

        # Mock the module's student_is_qualified method
        self.is_qualified = True
        self.original_student_is_qualified = certificate.student_is_qualified
        certificate.student_is_qualified = (
            lambda student, course: self.is_qualified)

    def tearDown(self):
        certificate.student_is_qualified = self.original_student_is_qualified
        super(CertificateHandlerTestCase, self).tearDown()

    def test_student_must_be_enrolled(self):
        # If student not in session, expect redirect
        response = self.get('/certificate')
        self.assertEquals(302, response.status_code)

        # If student is not enrolled, expect redirect
        actions.login('test@example.com')
        response = self.get('/certificate')
        self.assertEquals(302, response.status_code)
        self.assertEquals(
            'http://localhost/course', response.headers['Location'])

        # If the student is enrolled, expect certificate
        models.Student.add_new_student_for_current_user('Test User', None, self)
        response = self.get('/certificate')
        self.assertEquals(200, response.status_code)

    def test_student_must_be_qualified(self):
        actions.login('test@example.com')
        models.Student.add_new_student_for_current_user('Test User', None, self)

        # If student is not qualified, expect redirect to home page
        self.is_qualified = False
        response = self.get('/certificate')
        self.assertEquals(302, response.status_code)
        self.assertEquals('http://localhost/', response.headers['Location'])

        # If student is qualified, expect certificate
        self.is_qualified = True
        response = self.get('/certificate')
        self.assertEquals(200, response.status_code)

    def test_certificate_should_have_student_nickname(self):
        actions.login('test@example.com')
        models.Student.add_new_student_for_current_user('Jane Doe', None, self)

        response = self.get('/certificate')
        self.assertEquals(200, response.status_code)
        self.assertIn('Jane Doe', response.body)

    def test_download_pdf(self):
        actions.login('test@example.com')
        models.Student.add_new_student_for_current_user('Test User', None, self)

        response = self.get('/certificate.pdf')
        self.assertEqual('application/pdf', response.headers['Content-Type'])
        self.assertEqual(
            'attachment; filename=certificate.pdf',
            response.headers['Content-Disposition'])
        self.assertIn('/Title (Course Builder Certificate)', response.body)

    def test_certificate_table_entry(self):
        user = actions.login('test@example.com')
        models.Student.add_new_student_for_current_user('Test User', None, self)
        student = models.Student.get_by_user(user)

        all_courses = sites.get_all_courses()
        app_context = all_courses[0]
        course = courses.Course(None, app_context=app_context)

        # If the student is qualified, a link is shown
        self.is_qualified = True
        mock_handler = MockHandler()
        table_entry = certificate.get_certificate_table_entry(
            mock_handler, student, course)
        self.assertEquals('Certificate', table_entry[0])
        link = str(table_entry[1])
        self.assertEquals(
            '<a href="certificate">Click for certificate</a> '
            '| <a href="certificate.pdf">Download PDF</a>', link)

        # If the student is not qualified, a message is shown
        self.is_qualified = False
        table_entry = certificate.get_certificate_table_entry(
            mock_handler, student, course)
        self.assertEquals('Certificate', table_entry[0])
        self.assertIn(
            'You have not yet met the course requirements', table_entry[1])


class CertificateCriteriaTestCase(actions.TestBase):
    """Tests the different certificate criteria configurations."""

    COURSE_NAME = 'certificate_criteria'
    STUDENT_EMAIL = 'foo@foo.com'
    TEST_USER = None
    ADMIN_EMAIL = 'admin@foo.com'
    ANALYTICS_URL = ('/' + COURSE_NAME +
                     '/dashboard?action=analytics_certificates_earned')

    def setUp(self):
        super(CertificateCriteriaTestCase, self).setUp()
        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Certificate Criteria')

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, context)
        self.course.save()
        self.TEST_USER = actions.login('foo@foo.com')
        actions.register(self, self.TEST_USER.email())
        self.student = (
            models.StudentProfileDAO.get_enrolled_student_by_user_for(
                self.TEST_USER, context))

        # Override course.yaml settings by patching app_context.
        self.get_environ_old = sites.ApplicationContext.get_environ
        self.certificate_criteria = []

        def get_environ_new(app_context):
            environ = self.get_environ_old(app_context)
            environ['certificate_criteria'] = self.certificate_criteria
            return environ

        sites.ApplicationContext.get_environ = get_environ_new

    def tearDown(self):
        # Clean up app_context.
        sites.ApplicationContext.get_environ = self.get_environ_old
        namespace_manager.set_namespace(self.old_namespace)
        super(CertificateCriteriaTestCase, self).tearDown()

    def _assert_redirect_to_course_landing_page(self, response):
        self.assertEquals(302, response.status_code)
        self.assertEquals('http://localhost/' + self.COURSE_NAME + '/', (
            response.headers['Location']))

    def test_no_criteria(self):
        response = self.get('certificate')
        self._assert_redirect_to_course_landing_page(response)

    def _run_analytic_and_expect(self, expected_students,
                                 expected_active_students,
                                 expected_certificates):
        actions.login(self.ADMIN_EMAIL)
        response = self.get(self.ANALYTICS_URL)
        self.submit(response.forms['gcb-run-visualization-certificates_earned'],
                    response)
        self.execute_all_deferred_tasks()

        dom = self.parse_html_string(self.get(self.ANALYTICS_URL).body)
        total_students = int(
            dom.find('.//span[@id="total_students"]').text)
        total_active_students = int(
            dom.find('.//span[@id="total_active_students"]').text)
        total_certificates = int(
            dom.find('.//span[@id="total_certificates"]').text)
        self.assertEquals(expected_students, total_students)
        self.assertEquals(expected_active_students, total_active_students)
        self.assertEquals(expected_certificates, total_certificates)
        actions.login(self.STUDENT_EMAIL)

    def test_no_criteria_analytic(self):
        self._run_analytic_and_expect(1, 0, 0)

    def test_machine_graded(self):
        assessment = self.course.add_assessment()
        assessment.title = 'Assessment'
        assessment.html_content = 'assessment content'
        assessment.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        self.certificate_criteria.append(
            {'assessment_id': assessment.unit_id, 'pass_percent': 70.0})

        # Student has not yet completed assessment, expect redirect to home page
        response = self.get('certificate')
        self._assert_redirect_to_course_landing_page(response)
        self._run_analytic_and_expect(1, 0, 0)  # 1 student, 0 active, no cert.

        # Submit assessment with low score
        actions.submit_assessment(
            self,
            assessment.unit_id,
            {'answers': '', 'score': 50.0,
             'assessment_type': assessment.unit_id},
            presubmit_checks=False
        )

        response = self.get('certificate')
        self._assert_redirect_to_course_landing_page(response)
        self._run_analytic_and_expect(1, 1, 0)  # 1 student, 1 active, no cert

        # Submit assessment with expected score
        actions.submit_assessment(
            self,
            assessment.unit_id,
            {'answers': '', 'score': 70,
             'assessment_type': assessment.unit_id},
            presubmit_checks=False
        )

        response = self.get('certificate')
        self.assertEquals(200, response.status_code)
        self._run_analytic_and_expect(1, 1, 1)  # 1 student, 1 active, 1 cert

    def _submit_review(self, assessment):
        """Submits a review by the current student.

        Creates a new user that completes the assessment as well,
        so that the student can review it.

        Args:
            assessment: The assessment to review.
        """

        reviewer_key = self.student.get_key()
        reviewee = models.Student(key_name='reviewee@example.com')
        reviewee_key = reviewee.put()

        submission_key = db.Key.from_path(
            student_work.Submission.kind(),
            student_work.Submission.key_name(
                reviewee_key=reviewee_key, unit_id=str(assessment.unit_id)))
        summary_key = peer.ReviewSummary(
            assigned_count=1, reviewee_key=reviewee_key,
            submission_key=submission_key, unit_id=str(assessment.unit_id)
        ).put()
        review_key = student_work.Review(
            contents='old_contents', reviewee_key=reviewee_key,
            reviewer_key=reviewer_key, unit_id=str(assessment.unit_id)).put()
        step_key = peer.ReviewStep(
            assigner_kind=domain.ASSIGNER_KIND_HUMAN,
            review_key=review_key, review_summary_key=summary_key,
            reviewee_key=reviewee_key, reviewer_key=reviewer_key,
            submission_key=submission_key,
            state=domain.REVIEW_STATE_ASSIGNED, unit_id=str(assessment.unit_id)
        ).put()
        updated_step_key = review_module.Manager.write_review(
            step_key, 'new_contents')

        self.assertEqual(step_key, updated_step_key)

    def test_peer_graded(self):
        assessment = self.course.add_assessment()
        assessment.title = 'Assessment'
        assessment.html_content = 'assessment content'
        assessment.workflow_yaml = (
            '{grader: human,'
            'matcher: peer,'
            'review_due_date: \'2034-07-01 12:00\','
            'review_min_count: 1,'
            'review_window_mins: 20,'
            'submission_due_date: \'2034-07-01 12:00\'}')
        assessment.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        self.certificate_criteria.append(
            {'assessment_id': assessment.unit_id})

        response = self.get('certificate')
        self._assert_redirect_to_course_landing_page(response)

        actions.submit_assessment(
            self,
            assessment.unit_id,
            {'answers': '', 'assessment_type': assessment.unit_id},
            presubmit_checks=False
        )

        # Submitting assessment without doing required reviews is not enough
        response = self.get('certificate')
        self._assert_redirect_to_course_landing_page(response)

        # Submitting assessment together with required reviews is enough
        self._submit_review(assessment)

        response = self.get('certificate')
        self.assertEquals(200, response.status_code)

    def test_custom_criteria(self):
        def test_custom_criterion(unused_student, unused_course):
            return True

        CRITERION = 'test_custom_criterion'
        self.certificate_criteria.append(
            {'custom_criteria': CRITERION})

        setattr(custom_criteria, CRITERION, test_custom_criterion)
        custom_criteria.registration_table.append(CRITERION)

        response = self.get('certificate')
        self.assertEquals(200, response.status_code)

    def test_combination(self):
        # Add machine graded assessment
        machine_graded = self.course.add_assessment()
        machine_graded.title = 'Machine Graded'
        machine_graded.html_content = 'assessment content'
        machine_graded.availability = courses.AVAILABILITY_AVAILABLE
        # Add peer graded assessment
        peer_graded = self.course.add_assessment()
        peer_graded.title = 'Peer Graded'
        peer_graded.html_content = 'assessment content'
        peer_graded.workflow_yaml = (
            '{grader: human,'
            'matcher: peer,'
            'review_due_date: \'2034-07-01 12:00\','
            'review_min_count: 1,'
            'review_window_mins: 20,'
            'submission_due_date: \'2034-07-01 12:00\'}')
        peer_graded.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        self.certificate_criteria.extend([
            {'assessment_id': machine_graded.unit_id, 'pass_percent': 30},
            {'assessment_id': peer_graded.unit_id}])

        # Confirm that meeting one criterion is not sufficient
        actions.submit_assessment(
            self,
            machine_graded.unit_id,
            {'answers': '', 'score': 40,
             'assessment_type': machine_graded.unit_id},
            presubmit_checks=False
        )

        response = self.get('certificate')
        self._assert_redirect_to_course_landing_page(response)

        # Confirm that meeting both criteria is sufficient
        actions.submit_assessment(
            self,
            peer_graded.unit_id,
            {'answers': '', 'assessment_type': peer_graded.unit_id},
            presubmit_checks=False
        )

        self._submit_review(peer_graded)

        response = self.get('certificate')
        self.assertEquals(200, response.status_code)
