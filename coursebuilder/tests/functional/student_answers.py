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

"""Analytics for extracting facts based on StudentAnswerEntity entries."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import collections

from common import crypto
from common import utils as common_utils
from models import courses
from models import models
from models import transforms
from models.data_sources import utils as data_sources_utils
from tests.functional import actions

from google.appengine.ext import db

COURSE_NAME = 'test_course'
COURSE_TITLE = 'Test Course'
ADMIN_EMAIL = 'test@example.com'

AssessmentDef = collections.namedtuple('AssessmentDef',
                                       ['unit_id', 'title', 'html_content'])
EntityDef = collections.namedtuple('EntityDef',
                                   ['entity_class', 'entity_id',
                                    'entity_key_name', 'data'])

ASSESSMENTS = [
    AssessmentDef(
        1, 'One Question',
        '<question quid="4785074604081152" weight="1" '
        'instanceid="8TvGgbrrbZ49"></question><br>'),
    AssessmentDef(
        2, 'Groups And Questions',
        '<question quid="5066549580791808" weight="1" '
        'instanceid="zsgZ8dUMvJjz"></question><br>'
        '<question quid="5629499534213120" weight="1" '
        'instanceid="YlGaKQ2mnOPG"></question><br>'
        '<question-group qgid="5348024557502464" '
        'instanceid="YpoECeTunEpj"></question-group><br>'
        '<question-group qgid="5910974510923776" '
        'instanceid="FcIh3jyWOTbP"></question-group><br>'),
    AssessmentDef(
        3, 'All Questions',
        '<question quid="6192449487634432" weight="1" '
        'instanceid="E5P0a0bFB0EH"></question><br>'
        '<question quid="5629499534213120" weight="1" '
        'instanceid="DlfLRsko2QHb"></question><br>'
        '<question quid="5066549580791808" weight="1" '
        'instanceid="hGrEjnP13pMA"></question><br>'
        '<question quid="4785074604081152" weight="1" '
        'instanceid="knWukHJApaQh"></question><br>'),
]

ENTITIES = [
    # Questions -----------------------------------------------------------
    EntityDef(
        models.QuestionEntity, 4785074604081152, None,
        '{"question": "To produce maximum generosity, what should be the '
        'overall shape of the final protrusion?", "rows": 1, "columns": 1'
        '00, "defaultFeedback": "", "graders": [{"matcher": "case_insensi'
        'tive", "feedback": "", "score": "0.7", "response": "oblong"}, {"'
        'matcher": "case_insensitive", "feedback": "", "score": "0.3", "r'
        'esponse": "extended"}], "type": 1, "description": "Maximum gener'
        'osity protrusion shape", "version": "1.5", "hint": ""}'),
    EntityDef(
        models.QuestionEntity, 5066549580791808, None,
        '{"question": "Describe the shape of a standard trepanning hammer'
        '", "multiple_selections": false, "choices": [{"feedback": "", "s'
        'core": 0.0, "text": "Round"}, {"feedback": "", "score": 0.0, "te'
        'xt": "Square"}, {"feedback": "", "score": 1.0, "text": "Diamond"'
        '}, {"feedback": "", "score": 0.0, "text": "Pyramid"}], "type": 0'
        ', "description": "Trepanning hammer shape", "version": "1.5"}'),
    EntityDef(
        models.QuestionEntity, 5629499534213120, None,
        '{"question": "Describe an appropriate bedside manner for post-tr'
        'eatment patient interaction", "rows": 1, "columns": 100, "defaul'
        'tFeedback": "", "graders": [{"matcher": "case_insensitive", "fee'
        'dback": "", "score": "1.0", "response": "gentle"}, {"matcher": "'
        'case_insensitive", "feedback": "", "score": "0.8", "response": "'
        'caring"}], "type": 1, "description": "Post-treatement interactio'
        'n", "version": "1.5", "hint": ""}'),
    EntityDef(
        models.QuestionEntity, 6192449487634432, None,
        '{"question": "When making a personality shift, how hard should t'
        'he strike be?", "multiple_selections": true, "choices": [{"feedb'
        'ack": "", "score": -1.0, "text": "Light"}, {"feedback": "", "sco'
        're": 0.7, "text": "Medium"}, {"feedback": "", "score": 0.3, "tex'
        't": "Heavy"}, {"feedback": "", "score": -1.0, "text": "Crushing"'
        '}], "type": 0, "description": "Personality shift strike strength'
        '", "version": "1.5"}'),

    # Question Groups -----------------------------------------------------
    EntityDef(
        models.QuestionGroupEntity, 5348024557502464, None,
        '{"description": "One MC, one SA", "introduction": "", "version":'
        '"1.5", "items": [{"question": 5066549580791808, "weight": "1"}, '
        '{"question": 6192449487634432, "weight": "1"}]}'),
    EntityDef(
        models.QuestionGroupEntity, 5910974510923776, None,
        '{"description": "All Questions", "introduction": "All questions"'
        ', "version": "1.5", "items": [{"question": 4785074604081152, "we'
        'ight": "0.25"}, {"question": 5066549580791808, "weight": "0.25"}'
        ', {"question": 5629499534213120, "weight": "0.25"}, {"question":'
        '6192449487634432, "weight": "0.25"}]}'),

    # Student Answers -----------------------------------------------------
    EntityDef(
        models.StudentAnswersEntity, None, '115715231223232197316',
        '{"3": {"version": "1.5", "containedTypes": {"DlfLRsko2QHb": "SaQ'
        'uestion", "E5P0a0bFB0EH": "McQuestion", "hGrEjnP13pMA": "McQuest'
        'ion", "knWukHJApaQh": "SaQuestion"}, "hGrEjnP13pMA": [true, fals'
        'e, false, false], "knWukHJApaQh": {"response": "fronk"}, "DlfLRs'
        'ko2QHb": {"response": "phleem"}, "answers": {"DlfLRsko2QHb": "ph'
        'leem", "E5P0a0bFB0EH": [1], "hGrEjnP13pMA": [0], "knWukHJApaQh":'
        '"fronk"}, "E5P0a0bFB0EH": [false, true, false, false], "individu'
        'alScores": {"DlfLRsko2QHb": 0, "E5P0a0bFB0EH": 0.7, "hGrEjnP13pM'
        'A": 0, "knWukHJApaQh": 0}}, "2": {"version": "1.5", "containedTy'
        'pes": {"zsgZ8dUMvJjz": "McQuestion", "FcIh3jyWOTbP": ["SaQuestio'
        'n", "McQuestion", "SaQuestion", "McQuestion"], "YlGaKQ2mnOPG": "'
        'SaQuestion", "YpoECeTunEpj": ["McQuestion", "McQuestion"]}, "ans'
        'wers": {"zsgZ8dUMvJjz": [1], "FcIh3jyWOTbP": ["round", [1], "col'
        'd", [3]], "YlGaKQ2mnOPG": "gentle", "YpoECeTunEpj": [[2], [1]]},'
        '"FcIh3jyWOTbP": {"FcIh3jyWOTbP.2.5629499534213120": {"response":'
        '"cold"}, "FcIh3jyWOTbP.1.5066549580791808": [false, true, false,'
        'false], "FcIh3jyWOTbP.3.6192449487634432": [false, false, false,'
        'true], "FcIh3jyWOTbP.0.4785074604081152": {"response": "round"}}'
        ', "YlGaKQ2mnOPG": {"response": "gentle"}, "zsgZ8dUMvJjz": [false'
        ',true, false, false], "individualScores": {"zsgZ8dUMvJjz": 0, "F'
        'cIh3jyWOTbP": [0, 0, 0, 0], "YlGaKQ2mnOPG": 1, "YpoECeTunEpj": ['
        '1, 0.7]}, "YpoECeTunEpj": {"YpoECeTunEpj.0.5066549580791808": [f'
        'alse, false, true, false], "YpoECeTunEpj.1.6192449487634432": [f'
        'alse, true, false, false]}}, "1": {"containedTypes": {"8TvGgbrrb'
        'Z49": "SaQuestion"}, "version": "1.5", "answers": {"8TvGgbrrbZ49'
        '": "oblong"}, "individualScores": {"8TvGgbrrbZ49": 0.7}, "8TvGgb'
        'rrbZ49": {"response": "oblong"}}}'),
    EntityDef(
        models.StudentAnswersEntity, None, '187186200184131193542',
        '{"3": {"version": "1.5", "containedTypes": {"DlfLRsko2QHb": "SaQ'
        'uestion", "E5P0a0bFB0EH": "McQuestion", "hGrEjnP13pMA": "McQuest'
        'ion", "knWukHJApaQh": "SaQuestion"}, "hGrEjnP13pMA": [false, tru'
        'e, false, false], "knWukHJApaQh": {"response": "square"}, "DlfLR'
        'sko2QHb": {"response": "caring"}, "answers": {"DlfLRsko2QHb": "c'
        'aring", "E5P0a0bFB0EH": [1], "hGrEjnP13pMA": [1], "knWukHJApaQh"'
        ': "square"}, "E5P0a0bFB0EH": [false, true, false, false], "indiv'
        'idualScores": {"DlfLRsko2QHb": 0.8, "E5P0a0bFB0EH": 0.7, "hGrEjn'
        'P13pMA": 0, "knWukHJApaQh": 0}}, "2": {"version": "1.5", "contai'
        'nedTypes": {"zsgZ8dUMvJjz": "McQuestion", "FcIh3jyWOTbP": ["SaQu'
        'estion", "McQuestion", "SaQuestion", "McQuestion"], "YlGaKQ2mnOP'
        'G": "SaQuestion", "YpoECeTunEpj": ["McQuestion", "McQuestion"]},'
        ' "answers": {"zsgZ8dUMvJjz": [3], "FcIh3jyWOTbP": ["spazzle", [3'
        '], "gloonk", [3]], "YlGaKQ2mnOPG": "frink", "YpoECeTunEpj": [[0]'
        ', [0]]}, "FcIh3jyWOTbP": {"FcIh3jyWOTbP.2.5629499534213120": {"r'
        'esponse": "gloonk"}, "FcIh3jyWOTbP.1.5066549580791808": [false, '
        'false, false, true], "FcIh3jyWOTbP.3.6192449487634432": [false, '
        'false, false, true], "FcIh3jyWOTbP.0.4785074604081152": {"respon'
        'se": "spazzle"}}, "YlGaKQ2mnOPG": {"response": "frink"}, "zsgZ8d'
        'UMvJjz": [false, false, false, true], "individualScores": {"zsgZ'
        '8dUMvJjz": 0, "FcIh3jyWOTbP": [0, 0, 0, 0], "YlGaKQ2mnOPG": 0, "'
        'YpoECeTunEpj": [0, 0]}, "YpoECeTunEpj": {"YpoECeTunEpj.0.5066549'
        '580791808": [true, false, false, false], "YpoECeTunEpj.1.6192449'
        '487634432": [true, false, false, false]}}, "1": {"containedTypes'
        '": {"8TvGgbrrbZ49": "SaQuestion"}, "version": "1.5", "answers": '
        '{"8TvGgbrrbZ49": "spalpeen"}, "individualScores": {"8TvGgbrrbZ49'
        '": 0}, "8TvGgbrrbZ49": {"response": "spalpeen"}}}'),
]

EXPECTED_COURSE_UNITS = [
    {
        'title': 'One Question',
        'unit_id': '1',
        'now_available': True,
        'type': 'A',
    },
    {
        'title': 'Groups And Questions',
        'unit_id': '2',
        'now_available': True,
        'type': 'A',
    },
    {
        'title': 'All Questions',
        'unit_id': '3',
        'now_available': True,
        'type': 'A',
    }
]

EXPECTED_QUESTIONS = [
    {
        'question_id': '4785074604081152',
        'description': 'Maximum generosity protrusion shape',
        'choices': []
    },
    {
        'question_id': '5066549580791808',
        'description': 'Trepanning hammer shape',
        'choices': ['Round', 'Square', 'Diamond', 'Pyramid']
    },
    {
        'question_id': '5629499534213120',
        'description': 'Post-treatement interaction',
        'choices': []
    },
    {
        'question_id': '6192449487634432',
        'description': 'Personality shift strike strength',
        'choices': ['Light', 'Medium', 'Heavy', 'Crushing']
    }
]

EXPECTED_ANSWERS = [
    {'unit_id': '1', 'sequence': 0, 'count': 1, 'is_valid': True,
     'answer': 'oblong', 'question_id': '4785074604081152'},
    {'unit_id': '1', 'sequence': 0, 'count': 1, 'is_valid': False,
     'answer': 'spalpeen', 'question_id': '4785074604081152'},
    {'unit_id': '2', 'sequence': 0, 'count': 1, 'is_valid': True,
     'answer': '1', 'question_id': '5066549580791808'},
    {'unit_id': '2', 'sequence': 0, 'count': 1, 'is_valid': True,
     'answer': '3', 'question_id': '5066549580791808'},
    {'unit_id': '2', 'sequence': 1, 'count': 1, 'is_valid': True,
     'answer': 'gentle', 'question_id': '5629499534213120'},
    {'unit_id': '2', 'sequence': 1, 'count': 1, 'is_valid': False,
     'answer': 'frink', 'question_id': '5629499534213120'},
    {'unit_id': '2', 'sequence': 2, 'count': 1, 'is_valid': True,
     'answer': '0', 'question_id': '5066549580791808'},
    {'unit_id': '2', 'sequence': 2, 'count': 1, 'is_valid': True,
     'answer': '2', 'question_id': '5066549580791808'},
    {'unit_id': '2', 'sequence': 3, 'count': 1, 'is_valid': True,
     'answer': '0', 'question_id': '6192449487634432'},
    {'unit_id': '2', 'sequence': 3, 'count': 1, 'is_valid': True,
     'answer': '1', 'question_id': '6192449487634432'},
    {'unit_id': '2', 'sequence': 4, 'count': 1, 'is_valid': False,
     'answer': 'round', 'question_id': '4785074604081152'},
    {'unit_id': '2', 'sequence': 4, 'count': 1, 'is_valid': False,
     'answer': 'spazzle', 'question_id': '4785074604081152'},
    {'unit_id': '2', 'sequence': 5, 'count': 1, 'is_valid': True,
     'answer': '1', 'question_id': '5066549580791808'},
    {'unit_id': '2', 'sequence': 5, 'count': 1, 'is_valid': True,
     'answer': '3', 'question_id': '5066549580791808'},
    {'unit_id': '2', 'sequence': 6, 'count': 1, 'is_valid': False,
     'answer': 'cold', 'question_id': '5629499534213120'},
    {'unit_id': '2', 'sequence': 6, 'count': 1, 'is_valid': False,
     'answer': 'gloonk', 'question_id': '5629499534213120'},
    {'unit_id': '2', 'sequence': 7, 'count': 2, 'is_valid': True,
     'answer': '3', 'question_id': '6192449487634432'},
    {'unit_id': '3', 'sequence': 0, 'count': 2, 'is_valid': True,
     'answer': '1', 'question_id': '6192449487634432'},
    {'unit_id': '3', 'sequence': 1, 'count': 1, 'is_valid': True,
     'answer': 'caring', 'question_id': '5629499534213120'},
    {'unit_id': '3', 'sequence': 1, 'count': 1, 'is_valid': False,
     'answer': 'phleem', 'question_id': '5629499534213120'},
    {'unit_id': '3', 'sequence': 2, 'count': 1, 'is_valid': True,
     'answer': '0', 'question_id': '5066549580791808'},
    {'unit_id': '3', 'sequence': 2, 'count': 1, 'is_valid': True,
     'answer': '1', 'question_id': '5066549580791808'},
    {'unit_id': '3', 'sequence': 3, 'count': 1, 'is_valid': False,
     'answer': 'fronk', 'question_id': '4785074604081152'},
    {'unit_id': '3', 'sequence': 3, 'count': 1, 'is_valid': False,
     'answer': 'square', 'question_id': '4785074604081152'},
]


class StudentAnswersAnalyticsTest(actions.TestBase):

    def setUp(self):
        super(StudentAnswersAnalyticsTest, self).setUp()

        self.context = actions.simple_add_course(COURSE_NAME, ADMIN_EMAIL,
                                                 COURSE_TITLE)
        self.course = courses.Course(None, self.context)

        for assessment in ASSESSMENTS:
            self._add_assessment(self.course, assessment)
        self.course.save()
        for entity in ENTITIES:
            self._add_entity(self.context, entity)

    def _add_assessment(self, course, assessment_def):
        assessment = course.add_assessment()
        assessment.unit_id = assessment_def.unit_id
        assessment.title = assessment_def.title
        assessment.availability = courses.AVAILABILITY_AVAILABLE
        assessment.html_content = assessment_def.html_content

    def _add_entity(self, context, entity):
        with common_utils.Namespace(context.get_namespace_name()):
            if entity.entity_id:
                key = db.Key.from_path(entity.entity_class.__name__,
                                       entity.entity_id)
                to_store = entity.entity_class(data=entity.data, key=key)
            else:
                to_store = entity.entity_class(key_name=entity.entity_key_name,
                                               data=entity.data)
            to_store.put()

    def _get_data_source(self, source_name):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            data_sources_utils.DATA_SOURCE_ACCESS_XSRF_ACTION)
        url = ('/test_course/rest/data/%s/items?' % source_name +
               'data_source_token=%s&page_number=0' % xsrf_token)
        response = self.get(url)
        return transforms.loads(response.body)['data']

    def _verify_content(self, expected, actual):
        for expected_item, actual_item in zip(expected, actual):
            self.assertDictContainsSubset(expected_item, actual_item)

    def test_end_to_end(self):
        actions.login(ADMIN_EMAIL, is_admin=True)

        # Start map/reduce analysis job.
        response = self.get(
            '/test_course/dashboard?action=analytics_questions')
        form = response.forms['gcb-run-visualization-question_answers']
        self.submit(form, response)

        # Wait for map/reduce to run to completion.
        self.execute_all_deferred_tasks()

        # Verify output.
        course_units = self._get_data_source('course_units')
        self._verify_content(EXPECTED_COURSE_UNITS, course_units)
        course_questions = self._get_data_source('course_questions')
        self._verify_content(EXPECTED_QUESTIONS, course_questions)
        question_answers = self._get_data_source('question_answers')
        self._verify_content(EXPECTED_ANSWERS, question_answers)
