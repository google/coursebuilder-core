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
from models.data_sources import utils as data_sources_utils
from modules.questionnaire.questionnaire import QuestionnaireDataSource
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
        test_unit.availability = courses.AVAILABILITY_AVAILABLE
        test_lesson = self.course.add_lesson(test_unit)
        test_lesson.availability = courses.AVAILABILITY_AVAILABLE
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

    def register(self):
        user = actions.login(STUDENT_EMAIL, is_admin=False)
        actions.register(self, STUDENT_NAME)
        return models.Student.get_enrolled_student_by_user(user)


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
        data = StudentFormEntity.load_or_default(student, UNIQUE_FORM_ID)
        data.value = transforms.dumps(self.PAYLOAD_DICT)
        data.put()
        return data.value

    def test_rest_handler_right_data_retrieved(self):
        self.register()
        response = self._post_form_to_rest_handler(
            self._get_rest_request(self.PAYLOAD_DICT))
        self.assertEquals(200, response['status'])

    def test_rest_handler_requires_xsrf(self):
        response = self._post_form_to_rest_handler({'xsrf_token': 'BAD TOKEN'})
        self.assertEquals(403, response['status'])

    def test_rest_handler_only_allows_enrolled_user_to_submit(self):
        response = self._post_form_to_rest_handler(self._get_rest_request({}))
        self.assertEquals(401, response['status'])

        self.register()
        response = self._post_form_to_rest_handler(self._get_rest_request({}))
        self.assertEquals(200, response['status'])

    def test_form_data_in_datastore(self):
        student = self.register()
        self._put_data_in_datastore(student)
        response = StudentFormEntity.load_or_default(student, UNIQUE_FORM_ID)
        self.assertNotEqual(None, response)

    def test_form_data_can_be_retrieved(self):
        student = self.register()
        self._put_data_in_datastore(student)
        response = self._get_rest_request(self.PAYLOAD_DICT)
        self.assertEquals(self.PAYLOAD_DICT, response['payload'])


class QuestionnaireDataSourceTests(BaseQuestionnaireTests):
    FORM_0_DATA = [
        {u'name': u'title', u'value': u'War and Peace'},
        {u'name': u'rating', u'value': u'Long'}]
    FORM_1_DATA = [
        {u'name': u'country', u'value': u'Greece'},
        {u'name': u'lang', u'value': u'el_EL'},
        {u'name': u'tld', u'value': u'el'}]

    # Form 2 tests malformed data
    FORM_2_DATA = [
        {u'value': u'value without name'},  # missing 'name' field
        {u'name': u'name without value'},  # missing 'value' field
        {u'name': u'numeric', u'value': 3.14}]  # non-string value
    FORM_2_DATA_OUT = [
        {u'name': None, u'value': u'value without name'},
        {u'name': u'name without value', u'value': None},
        {u'name': u'numeric', u'value': u'3.14'}]


    def test_data_extraction(self):

        # Register a student and save some form values for that student
        student = self.register()

        entity = StudentFormEntity.load_or_default(student, 'form-0')
        entity.value = transforms.dumps({
            u'form_data': self.FORM_0_DATA})
        entity.put()

        entity = StudentFormEntity.load_or_default(student, u'form-1')
        entity.value = transforms.dumps({
            u'form_data': self.FORM_1_DATA})
        entity.put()

        entity = StudentFormEntity.load_or_default(student, u'form-2')
        entity.value = transforms.dumps({
            u'form_data': self.FORM_2_DATA})
        entity.put()

        # Log in as admin for the data query
        actions.logout()
        actions.login(ADMIN_EMAIL, is_admin=True)

        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            data_sources_utils.DATA_SOURCE_ACCESS_XSRF_ACTION)

        pii_secret = crypto.generate_transform_secret_from_xsrf_token(
            xsrf_token, data_sources_utils.DATA_SOURCE_ACCESS_XSRF_ACTION)

        safe_user_id = crypto.hmac_sha_2_256_transform(
            pii_secret, student.user_id)

        response = self.get(
            'rest/data/questionnaire_responses/items?'
            'data_source_token=%s&page_number=0' % xsrf_token)
        data = transforms.loads(response.body)['data']

        self.assertEqual(3, len(data))

        for index in range(3):
            self.assertIn(safe_user_id, data[index]['user_id'])
            self.assertEqual('form-%s' % index, data[index]['questionnaire_id'])

        self.assertEqual(self.FORM_0_DATA, data[0]['form_data'])
        self.assertEqual(self.FORM_1_DATA, data[1]['form_data'])
        self.assertEqual(self.FORM_2_DATA_OUT, data[2]['form_data'])

    def test_exportable(self):
        self.assertTrue(QuestionnaireDataSource.exportable())
