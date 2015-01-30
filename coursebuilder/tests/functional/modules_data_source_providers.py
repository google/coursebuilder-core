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

"""Tests for modules/data_source_providers/."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import datetime

import actions
from common import utils
from controllers import sites
from models import courses
from models import models
from models import transforms
from tests.functional import actions


class CourseElementsTest(actions.TestBase):

    def setUp(self):
        super(CourseElementsTest, self).setUp()
        sites.setup_courses('course:/test::ns_test, course:/:/')
        self._course = courses.Course(
            None, app_context=sites.get_all_courses()[0])
        actions.login('admin@google.com', is_admin=True)

    def test_assessments_schema(self):
        response = transforms.loads(self.get(
            '/test/rest/data/assessments/items').body)
        self.assertIn('unit_id', response['schema'])
        self.assertIn('title', response['schema'])
        self.assertIn('weight', response['schema'])
        self.assertIn('html_check_answers', response['schema'])
        self.assertIn('props', response['schema'])

    def test_units_schema(self):
        response = transforms.loads(self.get(
            '/test/rest/data/units/items').body)
        self.assertIn('unit_id', response['schema'])
        self.assertIn('title', response['schema'])
        self.assertIn('props', response['schema'])

    def test_lessons_schema(self):
        response = transforms.loads(self.get(
            '/test/rest/data/lessons/items').body)
        self.assertIn('lesson_id', response['schema'])
        self.assertIn('unit_id', response['schema'])
        self.assertIn('title', response['schema'])
        self.assertIn('scored', response['schema'])
        self.assertIn('has_activity', response['schema'])
        self.assertIn('activity_title', response['schema'])

    def test_no_assessments_in_course(self):
        response = transforms.loads(self.get(
            '/test/rest/data/assessments/items').body)
        self.assertListEqual([], response['data'])

    def test_no_units_in_course(self):
        response = transforms.loads(self.get(
            '/test/rest/data/units/items').body)
        self.assertListEqual([], response['data'])

    def test_no_lessons_in_course(self):
        response = transforms.loads(self.get(
            '/test/rest/data/lessons/items').body)
        self.assertListEqual([], response['data'])

    def test_one_assessment_in_course(self):
        title = 'Plugh'
        weight = 123
        html_check_answers = True
        properties = {'a': 456, 'b': 789}

        assessment1 = self._course.add_assessment()
        assessment1.title = title
        assessment1.weight = weight
        assessment1.html_check_answers = html_check_answers
        assessment1.properties = properties
        self._course.save()
        response = transforms.loads(self.get(
            '/test/rest/data/assessments/items').body)
        self.assertEquals(1, len(response['data']))
        self.assertEquals(title, response['data'][0]['title'])
        self.assertEquals(weight, response['data'][0]['weight'])
        self.assertEquals(html_check_answers,
                          response['data'][0]['html_check_answers'])
        self.assertEquals(transforms.dumps(properties),
                          response['data'][0]['props'])

    def test_one_unit_in_course(self):
        title = 'Plugh'
        properties = {'a': 456, 'b': 789}

        unit1 = self._course.add_unit()
        unit1.title = title
        unit1.properties = properties
        self._course.save()
        response = transforms.loads(self.get(
            '/test/rest/data/units/items').body)
        self.assertEquals(1, len(response['data']))
        self.assertEquals(title, response['data'][0]['title'])
        self.assertEquals(properties, response['data'][0]['props'])

    def test_one_lesson_in_course(self):
        title = 'Plover'
        scored = True
        has_activity = True
        activity_title = 'Xyzzy'

        unit1 = self._course.add_unit()
        lesson1 = self._course.add_lesson(unit1)
        lesson1.title = title
        lesson1.scored = scored
        lesson1.has_activity = has_activity
        lesson1.activity_title = activity_title
        self._course.save()
        response = transforms.loads(self.get(
            '/test/rest/data/lessons/items').body)
        self.assertEquals(1, len(response['data']))
        self.assertEquals(str(unit1.unit_id), response['data'][0]['unit_id'])
        self.assertEquals(title, response['data'][0]['title'])
        self.assertEquals(scored, response['data'][0]['scored'])
        self.assertEquals(has_activity, response['data'][0]['has_activity'])
        self.assertEquals(activity_title, response['data'][0]['activity_title'])

    def test_unit_and_assessment(self):
        self._course.add_assessment()
        self._course.add_unit()
        self._course.save()

        response = transforms.loads(self.get(
            '/test/rest/data/units/items').body)
        self.assertEquals(1, len(response['data']))
        self.assertEquals('New Unit', response['data'][0]['title'])

        response = transforms.loads(self.get(
            '/test/rest/data/assessments/items').body)
        self.assertEquals(1, len(response['data']))
        self.assertEquals('New Assessment', response['data'][0]['title'])

    def test_stable_ids(self):
        self._course.add_assessment()
        unit2 = self._course.add_unit()
        self._course.add_assessment()
        self._course.add_unit()
        self._course.add_assessment()
        self._course.add_unit()
        self._course.add_assessment()
        self._course.add_unit()
        self._course.add_assessment()
        self._course.add_unit()
        self._course.add_assessment()
        self._course.add_assessment()
        self._course.add_assessment()
        self._course.add_unit()
        self._course.save()

        response = transforms.loads(self.get(
            '/test/rest/data/units/items').body)
        self.assertListEqual(['2', '4', '6', '8', '10', '14'],
                             [u['unit_id'] for u in response['data']])

        self._course.delete_unit(unit2)
        self._course.save()

        response = transforms.loads(self.get(
            '/test/rest/data/units/items').body)
        self.assertListEqual(['4', '6', '8', '10', '14'],
                             [u['unit_id'] for u in response['data']])


class StudentsTest(actions.TestBase):

    def setUp(self):
        super(StudentsTest, self).setUp()
        sites.setup_courses('course:/test::ns_test, course:/:/')
        self._course = courses.Course(
            None, app_context=sites.get_all_courses()[0])
        actions.login('admin@google.com', is_admin=True)

    def test_students_schema(self):
        response = transforms.loads(self.get(
            '/test/rest/data/students/items').body)
        self.assertNotIn('name', response['schema'])
        self.assertNotIn('additional_fields', response['schema'])
        self.assertIn('enrolled_on', response['schema'])
        self.assertIn('user_id', response['schema'])
        self.assertIn('is_enrolled', response['schema'])

    def test_no_students(self):
        response = transforms.loads(self.get(
            '/test/rest/data/students/items').body)
        self.assertListEqual([], response['data'])

    def test_one_student(self):
        expected_enrolled_on = datetime.datetime.utcnow()
        user_id = '123456'
        is_enrolled = True
        with utils.Namespace('ns_test'):
            models.Student(user_id=user_id, is_enrolled=is_enrolled).put()

        response = transforms.loads(self.get(
            '/test/rest/data/students/items').body)
        self.assertEquals('None', response['data'][0]['user_id'])
        self.assertEquals(is_enrolled, response['data'][0]['is_enrolled'])
        # expected/actual enrolled_on timestamp may be _slightly_ off
        # since it's automatically set on creation by DB internals.
        # Allow for this.
        actual_enrolled_on = datetime.datetime.strptime(
            response['data'][0]['enrolled_on'],
            transforms.ISO_8601_DATETIME_FORMAT)
        self.assertAlmostEqual(
            0,
            abs((expected_enrolled_on - actual_enrolled_on).total_seconds()), 1)

    def test_modified_blacklist_schema(self):
        save_blacklist = models.Student._PROPERTY_EXPORT_BLACKLIST
        models.Student._PROPERTY_EXPORT_BLACKLIST = [
            'name',
            'additional_fields.age',
            'additional_fields.gender',
        ]
        response = transforms.loads(self.get(
            '/test/rest/data/students/items').body)
        self.assertNotIn('name', response['schema'])
        self.assertIn('enrolled_on', response['schema'])
        self.assertIn('user_id', response['schema'])
        self.assertIn('is_enrolled', response['schema'])
        self.assertIn('additional_fields', response['schema'])
        models.Student._PROPERTY_EXPORT_BLACKLIST = save_blacklist

    def test_modified_blacklist_contents(self):
        save_blacklist = models.Student._PROPERTY_EXPORT_BLACKLIST
        models.Student._PROPERTY_EXPORT_BLACKLIST = [
            'name',
            'additional_fields.age',
            'additional_fields.gender',
        ]
        blacklisted = [
            {'name': 'age', 'value': '22'},
            {'name': 'gender', 'value': 'female'},
        ]
        permitted = [
            {'name': 'goal', 'value': 'complete_course'},
            {'name': 'timezone', 'value': 'America/Los_Angeles'},
        ]
        additional_fields = transforms.dumps(
            [[x['name'], x['value']] for x in blacklisted + permitted])
        with utils.Namespace('ns_test'):
            models.Student(
                user_id='123456', additional_fields=additional_fields).put()
            response = transforms.loads(self.get(
                '/test/rest/data/students/items').body)
        self.assertEquals(permitted,
                          response['data'][0]['additional_fields'])
        models.Student._PROPERTY_EXPORT_BLACKLIST = save_blacklist


class StudentScoresTest(actions.TestBase):

    def setUp(self):
        super(StudentScoresTest, self).setUp()
        sites.setup_courses('course:/test::ns_test, course:/:/')
        self._course = courses.Course(
            None, app_context=sites.get_all_courses()[0])
        actions.login('admin@google.com', is_admin=True)

    def test_students_schema(self):
        response = transforms.loads(self.get(
            '/test/rest/data/assessment_scores/items').body)
        self.assertIn('user_id', response['schema'])
        self.assertIn('id', response['schema'])
        self.assertIn('title', response['schema'])
        self.assertIn('score', response['schema'])
        self.assertIn('weight', response['schema'])
        self.assertIn('completed', response['schema'])
        self.assertIn('human_graded', response['schema'])

    def test_no_students(self):
        response = transforms.loads(self.get(
            '/test/rest/data/assessment_scores/items').body)
        self.assertListEqual([], response['data'])

    def test_one_student_no_scores(self):
        with utils.Namespace('ns_test'):
            models.Student(user_id='123456').put()
        response = transforms.loads(self.get(
            '/test/rest/data/assessment_scores/items').body)
        self.assertListEqual([], response['data'])

    def _score_data(self, unit_id, title, weight, score, assessment_rank):
        return {
            'id': unit_id,
            'title': title,
            'weight': weight,
            'score': score,
            'user_id': 'None',
            'attempted': True,
            'completed': False,
            'human_graded': False,
            'user_rank': 0,
            'assessment_rank': assessment_rank,
            }

    def test_one_student_one_score(self):
        scores = '{"1": 20}'
        with utils.Namespace('ns_test'):
            self._course.add_assessment()
            self._course.save()
            models.Student(user_id='123456', scores=scores).put()
        response = transforms.loads(self.get(
            '/test/rest/data/assessment_scores/items').body)
        self.assertItemsEqual(
            [self._score_data('1', 'New Assessment', 1, 20, 0)],
            response['data'])

    def test_two_students_two_scores_each(self):
        s1_scores = '{"1": 20, "2": 30}'
        s2_scores = '{"1": 10, "2": 40}'
        with utils.Namespace('ns_test'):
            a1 = self._course.add_assessment()
            a1.title = 'A1'
            a1.weight = 1
            a2 = self._course.add_assessment()
            a2.title = 'A2'
            a2.weight = 2
            self._course.save()
            models.Student(user_id='1', scores=s1_scores).put()
            models.Student(user_id='2', scores=s2_scores).put()
        response = transforms.loads(self.get(
            '/test/rest/data/assessment_scores/items').body)
        self.assertItemsEqual([self._score_data('1', 'A1', 1, 20, 0),
                               self._score_data('1', 'A1', 1, 10, 0),
                               self._score_data('2', 'A2', 2, 30, 1),
                               self._score_data('2', 'A2', 2, 40, 1)],
                              response['data'])

    def test_two_students_partial_scores(self):
        s1_scores = '{"1": 20}'
        s2_scores = '{"1": 10, "2": 40}'
        with utils.Namespace('ns_test'):
            a1 = self._course.add_assessment()
            a1.title = 'A1'
            a1.weight = 1
            a2 = self._course.add_assessment()
            a2.title = 'A2'
            a2.weight = 2
            self._course.save()
            models.Student(user_id='1', scores=s1_scores).put()
            models.Student(user_id='2', scores=s2_scores).put()
        response = transforms.loads(self.get(
            '/test/rest/data/assessment_scores/items').body)
        self.assertItemsEqual([self._score_data('1', 'A1', 1, 20, 0),
                               self._score_data('1', 'A1', 1, 10, 0),
                               self._score_data('2', 'A2', 2, 40, 1)],
                              response['data'])
