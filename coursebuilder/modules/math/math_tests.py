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

"""Tests for the math module."""

__author__ = ['Gun Pinyo (gunpinyo@google.com)',
              'Neema Kotonya (neemak@google.com)']

from models import courses
from tests.functional import actions

COURSE_NAME = 'math_tag_test_course'
ADMIN_EMAIL = 'user@test.com'
MATHJAX_SCRIPT = """<script src="/modules/math/MathJax/MathJax.js?config=\
TeX-AMS-MML_HTMLorMML">"""
LATEX_SCRIPT = """<script type="math/tex">x^2+2x+1</script>"""


class MathTagTests(actions.TestBase):
    """Tests for the math content tag."""

    def setUp(self):
        super(MathTagTests, self).setUp()

        actions.login(ADMIN_EMAIL, is_admin=True)
        self.base = '/' + COURSE_NAME

        test_course = actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL,
                                                'Test Course')
        self.course = courses.Course(None, test_course)
        math_unit = self.course.add_unit()
        math_unit.title = 'math_test_unit'
        no_math_unit = self.course.add_unit()
        no_math_unit.title = 'no_math_test_unit'

        self.math_unit_id = math_unit.unit_id
        self.no_math_unit_id = no_math_unit.unit_id

        no_math_lesson = self.course.add_lesson(no_math_unit)
        no_math_lesson.title = 'Lesson without any mathematical formula.'
        no_math_lesson.objectives = 'This lesson does not contain a math tag.'

        math_lesson = self.course.add_lesson(math_unit)
        math_lesson.title = 'First lesson with mathematical formula'
        math_lesson.objectives = (
            '<gcb-math input_type="TeX" instanceid="X99HibNGBIX4">'
            'x^2+2x+1'
            '</gcb-math><br>')

        self.course.save()

    def _search_element_lesson_body(self, search_element, assert_function,
                                    unit_id):
        """Base method for test_math_not_loaded() and test_math_loaded()."""
        for lesson in self.course.get_lessons(unit_id):
            response = self.get('unit?unit=%s&lesson=%s'
                                % (unit_id, lesson.lesson_id))
            assert_function(search_element, response.body)

    def test_mathjax_library_not_loaded_when_no_math_tag_present(self):
        self._search_element_lesson_body(MATHJAX_SCRIPT,
                                         actions.assert_does_not_contain,
                                         self.no_math_unit_id)

    def test_mathjax_library_is_loaded_when_math_tag_present(self):
        self._search_element_lesson_body(MATHJAX_SCRIPT, actions.assert_contains
                                         , self.math_unit_id)

    def test_same_formula_body(self):
        self._search_element_lesson_body(LATEX_SCRIPT, actions.assert_contains,
                                         self.math_unit_id)
