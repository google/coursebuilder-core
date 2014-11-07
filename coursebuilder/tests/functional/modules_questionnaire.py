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

"""Tests for the questionnaire module."""

__author__ = 'Neema Kotonya (neemak@google.com)'

from common import crypto
from controllers import sites
from models import courses
from models import models
from models import transforms
from modules.questionnaire.questionnaire import StudentFormEntity
from tests.functional import actions

from google.appengine.api import namespace_manager

COURSE_NAME = 'questionnaire_tag_test_course'
ADMIN_EMAIL = 'user@test.com'
UNIQUE_FORM_ID = 'This-is-the-unique-id-for-this-form'
STUDENT_EMAIL = 'student@foo.com'
STUDENT_NAME = 'A. Test Student'

TEST_FORM_HTML = """
<form id="This-is-the-unique-id-for-this-form">
    Course Name: <input name="course_name" type="text"  value=""><br>
    Unit Name: <input name="unit_name" type="text"  value=""><br>
</form>"""

QUESTIONNAIRE_TAG = """
<gcb-questionnaire
    form-id="This-is-the-unique-id-for-this-form"
    instanceid="hnWDW6Ld4RdO">
</gcb-questionnaire><br>
"""


class BaseQuestionnaireTests(actions.TestBase):
    """Tests for REST endpoint and tag renderer."""

    def setUp(self):
        super(BaseQuestionnaireTests, self).setUp()

        actions.login(ADMIN_EMAIL, is_admin=True)
        self.base = '/' + COURSE_NAME

        test_course = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Questionnaire Test Course')

        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % COURSE_NAME)

        self.course = courses.Course(None, test_course)
        test_unit = self.course.add_unit()
        test_unit.now_available = True
        test_lesson = self.course.add_lesson(test_unit)
        test_lesson.now_available = True
        test_lesson.title = 'This is a lesson that contains a form.'
        test_lesson.objectives = '%s\n%s' % (TEST_FORM_HTML, QUESTIONNAIRE_TAG)
        self.unit_id = test_unit.unit_id
        self.lesson_id = test_lesson.lesson_id
        self.course.save()

        actions.logout()

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(BaseQuestionnaireTests, self).tearDown()

    def get_button(self):
        dom = self.parse_html_string(self.get('unit?unit=%s&lesson=%s' % (
            self.unit_id, self.lesson_id)).body)
        return dom.find('.//button[@class="gcb-button questionnaire-button"]')


class QuestionnaireTagTests(BaseQuestionnaireTests):

    def test_submit_answers_button_out_of_session(self):
        button = self.get_button()
        self.assertEquals(UNIQUE_FORM_ID, button.attrib['data-form-id'])
        self.assertEquals('false', button.attrib['data-registered'])

    def test_submit_answers_button_in_session_no_student(self):
        actions.login(STUDENT_EMAIL, is_admin=False)
        button = self.get_button()
        self.assertEquals(UNIQUE_FORM_ID, button.attrib['data-form-id'])
        self.assertEquals('false', button.attrib['data-registered'])

    def test_submit_answers_button_student_in_session(self):
        actions.login(STUDENT_EMAIL, is_admin=False)
        actions.register(self, STUDENT_NAME)
        button = self.get_button()
        self.assertEquals(UNIQUE_FORM_ID, button.attrib['data-form-id'])
        self.assertEquals('true', button.attrib.get('data-registered'))


class QuestionnaireRESTHandlerTests(BaseQuestionnaireTests):

    REST_URL = 'rest/modules/questionnaire'
    PAYLOAD_DICT = {
        'form_data': [
            {u'query': u''},
            {u'course_name': u'course_name'},
            {u'unit_name': u'unit_name'}]}

    def _register(self):
        actions.login(STUDENT_EMAIL, is_admin=False)
        actions.register(self, STUDENT_NAME)
        return models.Student.get_enrolled_student_by_email(STUDENT_EMAIL)

    def _post_form_to_rest_handler(self, request_dict):
        return transforms.loads(self.post(
            self.REST_URL,
            {'request': transforms.dumps(request_dict)}).body)

    def _get_rest_request(self, payload_dict):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            'questionnaire')
        return {
            'xsrf_token': xsrf_token,
            'payload': payload_dict
        }

    def _put_data_in_datastore(self, student):
        data = StudentFormEntity.load_or_create(student, UNIQUE_FORM_ID)
        data.value = transforms.dumps(self.PAYLOAD_DICT)
        data.put()
        return data.value

    def test_rest_handler_right_data_retrieved(self):
        self._register()
        response = self._post_form_to_rest_handler(
            self._get_rest_request(self.PAYLOAD_DICT))
        self.assertEquals(200, response['status'])

    def test_rest_handler_requires_xsrf(self):
        response = self._post_form_to_rest_handler({'xsrf_token': 'BAD TOKEN'})
        self.assertEquals(403, response['status'])

    def test_rest_handler_only_allows_enrolled_user_to_submit(self):
        response = self._post_form_to_rest_handler(self._get_rest_request({}))
        self.assertEquals(401, response['status'])

        self._register()
        response = self._post_form_to_rest_handler(self._get_rest_request({}))
        self.assertEquals(200, response['status'])

    def test_form_data_in_datastore(self):
        student = self._register()
        self._put_data_in_datastore(student)
        response = StudentFormEntity.load_or_create(student, UNIQUE_FORM_ID)
        self.assertNotEqual(None, response)

    def test_form_data_can_be_retrieved(self):
        student = self._register()
        self._put_data_in_datastore(student)
        response = self._get_rest_request(self.PAYLOAD_DICT)
        self.assertEquals(self.PAYLOAD_DICT, response['payload'])
