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

"""Tests for the code_tags module."""

__author__ = 'Gun Pinyo (gunpinyo@google.com)'

from models import courses
from tests.functional import actions


class CodeTagTests(actions.TestBase):
    """Tests for the code example tags."""

    COURSE_NAME = 'code_tags_test_course'
    ADMIN_EMAIL = 'user@test.com'
    CODE_TYPE = 'javascript'
    CODE_EXAMPLE = (
        'function main() {'
        '    alert("hi");'
        '}'
        'main();')
    CODE_TAG_TEMPLATE = (
        '<gcb-code mode="%s" instanceid="my-instance">%s</gcb-code>')
    CODE_MIRROR_URL = '/static/codemirror/lib/codemirror.js'

    def setUp(self):
        super(CodeTagTests, self).setUp()

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        self.base = '/' + self.COURSE_NAME

        app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Test Course')
        self.course = courses.Course(None, app_context=app_context)

        self.code_tag_unit = self.course.add_unit()
        self.code_tag_unit.title = 'code_tag_test_unit'
        self.code_tag_unit.unit_header = self.CODE_TAG_TEMPLATE % (
            self.CODE_TYPE, self.CODE_EXAMPLE)

        self.no_code_tag_unit = self.course.add_unit()
        self.no_code_tag_unit.title = 'no_code_tag_test_unit'
        self.no_code_tag_unit.unit_header = 'Unit without code example tags.'

        self.course.save()

    def _get_unit_page(self, unit):
        return self.parse_html_string(
            self.get('unit?unit=%s' % unit.unit_id).body)

    def _get_script_element(self, unit):
        return self._get_unit_page(unit).find(
            './/script[@src="%s"]' % self.CODE_MIRROR_URL)

    def test_code_tag_rendered(self):
        code_elt = self._get_unit_page(self.code_tag_unit).find(
            './/code[@class="codemirror-container-readonly"]')
        self.assertEquals(self.CODE_TYPE, code_elt.attrib['data-mode'])
        self.assertEquals(self.CODE_EXAMPLE, code_elt.text)

    def test_codemirror_not_loaded_when_no_code_tags_present(self):
        self.assertIsNone(self._get_script_element(self.no_code_tag_unit))

    def test_codemirror_loaded_when_enabled_and_code_tags_present(self):
        self.assertIsNotNone(self._get_script_element(self.code_tag_unit))
