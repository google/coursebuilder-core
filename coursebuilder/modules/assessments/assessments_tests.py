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

"""Functional tests for assessments"""

__author__ = 'John Orr (jorr@google.com)'

import urlparse
from xml import etree
import yaml

from controllers import sites
from models import courses
from models import transforms
from tests.functional import actions

ADMIN_EMAIL = 'admin@foo.com'
STUDENT_EMAIL = 'student@foo.com'
STUDENT_NAME = 'A S Tudent'
COURSE_NAME = 'assessment_tests'
DUE_DATE_IN_PAST = '1995-06-15 12:00'
DUE_DATE_IN_FUTURE = '2035-06-15 12:00'


class EmbeddedAssessmentTests(actions.TestBase):

    def setUp(self):
        super(EmbeddedAssessmentTests, self).setUp()

        self.base = '/' + COURSE_NAME
        self.app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Learning Resources')
        self.course = courses.Course(None, self.app_context)
        self.assessment = self.course.add_assessment()
        self.assessment.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

        self.embed_url = 'modules/embed/v1/resource/assessment/%s' % (
            self.assessment.unit_id)

        actions.login(STUDENT_EMAIL, is_admin=False)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        super(EmbeddedAssessmentTests, self).tearDown()

    def set_workflow_field(self, name, value):
        workflow_dict = {}
        if self.assessment.workflow_yaml:
            workflow_dict = yaml.safe_load(self.assessment.workflow_yaml)
        workflow_dict[name] = value
        self.assessment.workflow_yaml = yaml.safe_dump(workflow_dict)
        self.course.save()

    def test_assessment_is_embedded(self):
        response = self.get(self.embed_url)
        self.assertEquals(302, response.status_int)
        redirect_url = response.headers['Location']
        dom = self.parse_html_string(self.get(redirect_url).body)
        self.assertEquals('hide-controls', dom.attrib['class'])

    def test_returns_to_assessment_after_grading(self):
        # Read the assessment grading URI from the assessment page
        redirect_url = self.get(self.embed_url).headers['Location']
        dom = self.parse_html_string(self.get(redirect_url).body)
        div = dom.find('.//div[@data-unit-id="%s"]' % self.assessment.unit_id)
        xsrf_token = div.get('data-xsrf-token')
        grader_uri = div.get('data-grader-uri')
        self.assertEquals('answer?embedded=true', grader_uri)

        # Post a response to the provided grading URI and examine redirect URI
        post_args = {
            'assessment_type': self.assessment.unit_id,
            'score': '0.0',
            'xsrf_token': xsrf_token
        }
        response = self.post(grader_uri, post_args)
        self.assertEquals(302, response.status_int)
        redirect_uri = response.headers['Location']
        parsed_uri = urlparse.urlparse(redirect_uri)
        self.assertEquals('/%s/assessment' % COURSE_NAME, parsed_uri.path)
        actual_query = urlparse.parse_qs(parsed_uri.query)
        expected_query = {
            'onsubmit': ['true'],
            'name': [str(self.assessment.unit_id)],
            'embedded': ['true']
        }
        self.assertEquals(expected_query, actual_query)

        # Confirm that the redirect uri is embeded
        response_body = self.get(redirect_uri).body
        dom = self.parse_html_string(response_body)
        self.assertEquals('hide-controls', dom.attrib['class'])
        # The confirmation message is shown
        self.assertIn(
            'cbShowMsgAutoHide(\'Assessment submitted.\')', response_body)

    def test_peer_review_is_not_embeddable(self):
        self.assessment.workflow_yaml = yaml.safe_dump({'grader': 'human'})
        self.course.save()
        redirect_url = self.get(self.embed_url).headers['Location']
        dom = self.parse_html_string(self.get(redirect_url).body)
        self.assertEquals('hide-controls', dom.attrib['class'])
        self.assertEquals(
            'Peer-review assignments cannot be embedded in external pages.',
            dom.find('.//*[@class="gcb-article"]').text.strip())

    def test_email_of_record_is_shown_to_student(self):
        def assert_message_and_email(message):
            # The message and email are seen in embedded assessments
            redirect_url = self.get(self.embed_url).headers['Location']
            response = self.get(redirect_url)
            dom = self.parse_html_string(response.body)
            top_info = etree.ElementTree.tostring(
                dom.find('.//*[@class="assessment-top-info"]'))
            self.assertIn(message, top_info)
            self.assertIn(STUDENT_EMAIL, top_info)

            # The message and email are not shown in non-embedded assessments
            response = self.get('assessment?name=%s' % self.assessment.unit_id)
            dom = self.parse_html_string(response.body)
            top_info = etree.ElementTree.tostring(
                dom.find('.//*[@class="assessment-top-info"]'))
            self.assertNotIn(message, top_info)
            self.assertNotIn(STUDENT_EMAIL, top_info)

        # Assessment is open, and no answers recorded
        assert_message_and_email(
            'Your answers will be recorded under the email')

        # Assessment is closed, and no answers recorded
        self.set_workflow_field('submission_due_date', DUE_DATE_IN_PAST)
        assert_message_and_email(
            'You have not submitted any answers to this assignment under the '
            'email')

        # Submit assignment
        self.set_workflow_field('submission_due_date', DUE_DATE_IN_FUTURE)
        actions.submit_assessment(self, self.assessment.unit_id, {
            'assessment_type': self.assessment.unit_id,
            'score': '75.0',
            'answers': transforms.dumps({
                'rawScore': 3,
                'totalWeight': 4,
                'percentScore': 75})
        })

        # Assessment is open, and some answers recorded
        assert_message_and_email(
            'Your answers will be recorded under the email')

        # Assessment is closed, and some answers recorded
        self.set_workflow_field('submission_due_date', DUE_DATE_IN_PAST)
        assert_message_and_email(
            'Your answers have been recorded under the email')


class AssessmentsTests(actions.TestBase):

    def setUp(self):
        super(AssessmentsTests, self).setUp()
        self.app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Some say he wears parsley in his ears')
        self.course = courses.Course(None, self.app_context)
        self.base = '/' + COURSE_NAME
        self.assessment = self.course.add_assessment()
        self.assessment.availability = courses.AVAILABILITY_AVAILABLE
        self.assessment.workflow_yaml = yaml.safe_dump({
            'grader': 'human',
            'matcher': 'peer',
            'review_due_date': None,
            'review_min_count': 0,
            'review_window_mins': 0,
            'show_feedback': False,
            'single_submission': False,
            'submission_due_date': None,  # The setting we are testing.
        })
        self.course.save()

    def tearDown(self):
        super(AssessmentsTests, self).tearDown()

    def test_submit_peer_reviewed_assessment_with_no_due_date(self):
        # Just looking to not get an exception on submission_due_date being
        # None.
        actions.login(STUDENT_EMAIL, is_admin=False)
        actions.register(self, 'John Smith')
        actions.submit_assessment(self, self.assessment.unit_id, {
            'assessment_type': self.assessment.unit_id,
            'score': '75.0',
            'answers': transforms.dumps({
                'rawScore': 3,
                'totalWeight': 4,
                'percentScore': 75})
        })
