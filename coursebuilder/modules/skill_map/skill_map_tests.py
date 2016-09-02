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

"""Tests for the skill mapping module."""

__author__ = 'John Orr (jorr@google.com)'

import cgi
import json
import cStringIO
import StringIO
import time
import urllib
import zipfile

from babel.messages import pofile
from networkx import DiGraph
from xml.etree import cElementTree

from common import crypto
from common import resource
from common import users
from controllers import sites
from models import courses
from models import jobs
from models import models
from models import transforms
from models.progress import UnitLessonCompletionTracker
from modules.i18n_dashboard import i18n_dashboard
from modules.skill_map import competency
from modules.skill_map.constants import SKILLS_KEY
from modules.skill_map.skill_map import HEADER_CALLBACKS
from modules.skill_map.skill_map import CountSkillCompletion
from modules.skill_map.skill_map import ResourceSkill
from modules.skill_map.skill_map import Skill
from modules.skill_map.skill_map import SkillAggregateRestHandler
from modules.skill_map.skill_map import SkillGraph
from modules.skill_map.skill_map import SkillMap
from modules.skill_map.skill_map import SkillRestHandler
from modules.skill_map.skill_map import SkillCompletionAggregate
from modules.skill_map.skill_map import _SkillDao
from modules.skill_map.skill_map import SkillCompletionTracker
from modules.skill_map.skill_map import SkillMapDataSource
from modules.skill_map.skill_map import TranslatableResourceSkill
from modules.skill_map.skill_map_metrics import SkillMapMetrics
from modules.skill_map.skill_map_metrics import CHAINS_MIN_LENGTH
from modules.skill_map.recommender import SkillRecommender
from rdflib import Graph
from tests.functional import actions

from google.appengine.api import namespace_manager

ADMIN_EMAIL = 'admin@foo.com'
COURSE_NAME = 'skill_map_course'

SKILL_NAME = 'rock climbing'
SKILL_DESC = 'Knows how to climb rocks'

SKILL_NAME_2 = 'ice skating'
SKILL_DESC_2 = 'Knows how to ice skate'

SKILL_NAME_3 = 'skiing'
SKILL_DESC_3 = 'Knows how to ski'


class BaseSkillMapTests(actions.TestBase):

    def setUp(self):
        super(BaseSkillMapTests, self).setUp()

        self.base = '/' + COURSE_NAME
        self.app_context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Skills Map Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % COURSE_NAME)

        self.course = courses.Course(None, self.app_context)
        self.setSkillWidgetSetting(on=True)

    def tearDown(self):
        self.setSkillWidgetSetting(on=False)
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(BaseSkillMapTests, self).tearDown()

    def setSkillWidgetSetting(self, on=True):
        settings = self.course.get_environ(self.app_context)
        settings['course']['display_skill_widget'] = on
        self.course.save_settings(settings)

    def _build_sample_graph(self):
        # a
        #  \
        #   d
        #  /
        # b
        # c--e--f
        self.skill_graph = SkillGraph.load()
        self.sa = self.skill_graph.add(Skill.build('a', ''))
        self.sb = self.skill_graph.add(Skill.build('b', ''))
        self.sd = self.skill_graph.add(Skill.build('d', ''))
        self.skill_graph.add_prerequisite(self.sd.id, self.sa.id)
        self.skill_graph.add_prerequisite(self.sd.id, self.sb.id)

        self.sc = self.skill_graph.add(Skill.build('c', ''))
        self.se = self.skill_graph.add(Skill.build('e', ''))
        self.skill_graph.add_prerequisite(self.se.id, self.sc.id)

        self.sf = self.skill_graph.add(Skill.build('f', ''))
        self.skill_graph.add_prerequisite(self.sf.id, self.se.id)

    def _create_lessons(self):
        """Creates 3 lessons for unit 1."""
        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.lesson1 = self.course.add_lesson(self.unit)
        self.lesson1.title = 'Test Lesson 1'
        self.lesson2 = self.course.add_lesson(self.unit)
        self.lesson2.title = 'Test Lesson 2'
        self.lesson3 = self.course.add_lesson(self.unit)
        self.lesson3.title = 'Test Lesson 3'
        self.unit2 = self.course.add_unit()
        self.unit.title = 'Test Unit 2'
        self.lesson4 = self.course.add_lesson(self.unit2)
        self.lesson4.title = 'Test Lesson 4'

    def _create_mc_question(self, description):
        """Create a multi-choice question."""

        mc_dict = {
            'description': description,
            'type': models.QuestionDTO.MULTIPLE_CHOICE,
            'choices': [
                {
                    'text': 'correct answer',
                    'score': 1.0
                },
                {
                    'text': 'incorrect answer',
                    'score': 0.0
                }],
            'version': '1.5'
        }
        question = models.QuestionDTO(None, mc_dict)
        qid = models.QuestionDAO.save(question)
        return models.QuestionDAO.load(qid)

    def _create_question_group(self, description, questions_list):
        qg_dict = {
            'description': description,
            'introduction': '',
            'items': [
                {'weight': 1, 'question': question.id}
                for question in questions_list],
            'version': '1.5'
        }
        question_group = models.QuestionGroupDTO(None, qg_dict)
        qgid = models.QuestionGroupDAO.save(question_group)
        return models.QuestionGroupDAO.load(qgid)


class SkillGraphTests(BaseSkillMapTests):

    def test_add_skill(self):
        # Skill map is initially empty
        skill_graph = SkillGraph.load()
        self.assertEqual(0, len(skill_graph.skills))

        # Add a single skill
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        self.assertEqual(1, len(skill_graph.skills))

        # Retrieve the skill by id
        self.assertEqual(SKILL_NAME, skill.name)
        self.assertEqual(SKILL_DESC, skill.description)

    def test_add_skill_twice_is_rejected(self):
        skill_graph = SkillGraph.load()

        # Add a single skill
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        self.assertEqual(1, len(skill_graph.skills))

        # Retrieve the skill by id and add it again
        with self.assertRaises(AssertionError):
            skill_graph.add(skill)

    def test_delete_skill(self):
        # Skill map is initially empty
        skill_graph = SkillGraph.load()
        self.assertEqual(0, len(skill_graph.skills))

        # Add a single skill
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        self.assertEqual(1, len(skill_graph.skills))

        # Delete the skill and expect empty
        skill_graph.delete(skill.id)
        self.assertEqual(0, len(skill_graph.skills))

    def test_delete_skill_with_successors(self):
        skill_graph = SkillGraph.load()

        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        skill_2 = skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))

        # Skill 1 is a prerequisite for Skill 2
        skill_graph.add_prerequisite(skill_2.id, skill_1.id)

        skill_graph.delete(skill_1.id)
        self.assertEqual(1, len(skill_graph.skills))
        self.assertEqual(skill_2, skill_graph.skills[0])
        self.assertEqual(0, len(skill_graph.prerequisites(skill_2.id)))

    def test_add_prerequisite(self):
        skill_graph = SkillGraph.load()

        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        skill_2 = skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))

        # Skill 1 is a prerequisite for Skill 2
        skill_graph.add_prerequisite(skill_2.id, skill_1.id)

        skill_graph = SkillGraph.load()
        self.assertEqual(1, len(skill_graph.prerequisites(skill_2.id)))
        self.assertEqual(
            skill_1.id, skill_graph.prerequisites(skill_2.id)[0].id)

        self.assertEqual(1, len(skill_graph.successors(skill_1.id)))
        self.assertEqual(
            skill_2.id, skill_graph.successors(skill_1.id)[0].id)

    def test_add_missing_prerequisites_rejected(self):
        skill_graph = SkillGraph.load()

        with self.assertRaises(AssertionError):
            skill_graph.add_prerequisite('missing', 'also missing')

        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))

        with self.assertRaises(AssertionError):
            skill_graph.add_prerequisite('missing', skill_1.id)

        with self.assertRaises(AssertionError):
            skill_graph.add_prerequisite(skill_1.id, 'also missing')

    def test_add_loop_rejected(self):
        """Test that cannot add a skill with a length-1 cycle."""
        skill_graph = SkillGraph.load()

        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))

        with self.assertRaises(AssertionError):
            skill_graph.add_prerequisite(skill_1.id, skill_1.id)

    def test_add_duplicate_prerequisites_rejected(self):
        skill_graph = SkillGraph.load()

        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        skill_2 = skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))

        skill_graph.add_prerequisite(skill_2.id, skill_1.id)
        with self.assertRaises(AssertionError):
            skill_graph.add_prerequisite(skill_2.id, skill_1.id)

    def test_delete_prerequisite(self):
        skill_graph = SkillGraph.load()

        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        skill_2 = skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))
        skill_3 = skill_graph.add(Skill.build(SKILL_NAME_3, SKILL_DESC_3))

        # Skills 1 and 2 are prerequisites for Skill 3
        skill_graph.add_prerequisite(skill_3.id, skill_1.id)
        skill_graph.add_prerequisite(skill_3.id, skill_2.id)

        skill_graph = SkillGraph.load()
        self.assertEqual(2, len(skill_graph.prerequisites(skill_3.id)))

        # Delete skill 1 as a prerequisite and expect that only skill 2 is a
        # prerequisite now
        skill_graph.delete_prerequisite(skill_3.id, skill_1.id)

        self.assertEqual(1, len(skill_graph.prerequisites(skill_3.id)))
        self.assertEqual(
            skill_2.id, skill_graph.prerequisites(skill_3.id)[0].id)

    def test_delete_missing_prerequisites_rejected(self):
        skill_graph = SkillGraph.load()

        with self.assertRaises(AssertionError):
            skill_graph.delete_prerequisite('missing', 'also missing')

        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        skill_2 = skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))

        with self.assertRaises(AssertionError):
            skill_graph.delete_prerequisite('missing', skill_1.id)

        with self.assertRaises(AssertionError):
            skill_graph.delete_prerequisite(skill_1.id, 'also missing')

        # Also reject deletion of a prerequisite if the skill exists but is not
        # currently a prerequisite
        with self.assertRaises(AssertionError):
            skill_graph.delete_prerequisite(skill_1.id, skill_2.id)

    def test_multiple_successors(self):
        skill_graph = SkillGraph.load()

        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        skill_2 = skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))
        skill_3 = skill_graph.add(Skill.build(SKILL_NAME_3, SKILL_DESC_3))

        # Skills 2 and 3 are successors of Skill 1
        skill_graph.add_prerequisite(skill_2.id, skill_1.id)
        skill_graph.add_prerequisite(skill_3.id, skill_1.id)

        skill_graph = SkillGraph.load()
        successor_ids = {s.id for s in skill_graph.successors(skill_1.id)}
        self.assertEqual({skill_2.id, skill_3.id}, successor_ids)


class SkillMapTests(BaseSkillMapTests):

    def setUp(self):
        super(SkillMapTests, self).setUp()

        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.lesson1 = self.course.add_lesson(self.unit)
        self.lesson1.title = 'Test Lesson 1'
        self.lesson2 = self.course.add_lesson(self.unit)
        self.lesson2.title = 'Test Lesson 2'
        self.lesson3 = self.course.add_lesson(self.unit)
        self.lesson3.title = 'Test Lesson 3'
        self.course.save()
        self.user_id = 1

    def tearDown(self):
        self.course.clear_current()
        super(SkillMapTests, self).tearDown()

    def test_follow_on_skills(self):
        self._build_sample_graph()
        # a-d
        #  /
        # b
        # c--e--f
        skill_map = SkillMap.load(self.course)
        skills = skill_map.skills()

        sa = next(x for x in skills if x.name == 'a')
        self.assertEqual(1, len(sa.successors))
        self.assertEqual('d', sa.successors[0].name)

        sb = next(x for x in skills if x.name == 'b')
        self.assertEqual(1, len(sb.successors))
        self.assertEqual('d', sb.successors[0].name)

        sd = next(x for x in skills if x.name == 'd')
        self.assertEqual(0, len(sd.successors))

    def test_topo_sort(self):
        self._build_sample_graph()
        skill_map = SkillMap.load(self.course)
        self.assertEqual(6, len(skill_map.skills()))
        # verify topological co-sets. Allow access to code under test.
        # pylint: disable=protected-access
        expected = {
            0: set([self.sa.id, self.sb.id, self.sc.id]),
            1: set([self.se.id, self.sd.id]),
            2: set([self.sf.id])}
        for ind, co_set in enumerate(skill_map._topo_sort()):
            self.assertEqual(expected[ind], co_set)

        # verify sorting skills by lesson
        expected = ['a', 'b', 'd', 'c', 'e', 'f']
        self.assertEqual(
            expected,
            [s.name for s in skill_map.skills(sort_by='lesson')])

        # verify sorting skills by name
        expected = ['a', 'b', 'c', 'd', 'e', 'f']
        self.assertEqual(
            expected,
            [s.name for s in skill_map.skills(sort_by='name')])

        # verify sorting skills by prerequisites
        expected = ['a', 'b', 'c', 'd', 'e', 'f']
        actual = [s.name
                  for s in skill_map.skills(sort_by='prerequisites')]
        self.assertEqual(expected, actual)

    def test_get_lessons_for_skill(self):
        skill_graph = SkillGraph.load()
        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        skill_2 = skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))

        # lesson 1 has one skill
        self.lesson1.properties[SKILLS_KEY] = [skill_1.id]
        # lesson 2 has no skills
        # lesson 3 has both skills
        self.lesson3.properties[SKILLS_KEY] = [
                skill_1.id, skill_2.id]
        self.course.save()

        skill_map = SkillMap.load(self.course)

        lessons = skill_map.get_lessons_for_skill(skill_1)
        self.assertEqual(2, len(lessons))
        self.assertEqual(self.lesson1.lesson_id, lessons[0].lesson_id)
        self.assertEqual(self.lesson3.lesson_id, lessons[1].lesson_id)

        lessons = skill_map.get_lessons_for_skill(skill_2)
        self.assertEqual(1, len(lessons))
        self.assertEqual(self.lesson3.lesson_id, lessons[0].lesson_id)

    def test_get_lessons_returns_empty_list_when_no_skills_assigned(self):
        skill_graph = SkillGraph.load()
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))

        skill_map = SkillMap.load(self.course)

        # look up lessons by skill id
        lessons = skill_map.get_lessons_for_skill(skill)
        self.assertIsNotNone(lessons)
        self.assertEqual(0, len(lessons))

        # look up lessons by skill
        lessons = skill_map.get_lessons_for_skill(skill)
        self.assertIsNotNone(lessons)
        self.assertEqual(0, len(lessons))

    def test_skill_map_request_cache_invalidation(self):
        # verify that skill graph updates invalidate the cached skill map
        skill_graph = SkillGraph.load()
        skill_map_1 = SkillMap.load(self.course)
        skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        skill_map_2 = SkillMap.load(self.course)
        self.assertEqual(1, len(skill_map_2.skills()))
        self.assertNotEqual(skill_map_1, skill_map_2)

        # verify that the cached skill map is served
        # when there are no skill graph updates
        skill_map_3 = SkillMap.load(self.course)
        self.assertEqual(skill_map_2, skill_map_3)

    def test_personalized_skill_map_w_measures(self):
        """Test that measures are loaded for personalized skill maps."""

        self._build_sample_graph()
        skill_map = SkillMap.load(self.course, self.user_id)
        assert skill_map.personalized()
        skills = skill_map.skills()
        self.assertEqual(6, len(skills))
        for skill in skills:
            self.assertEqual(0.0, skill.score)
            self.assertEqual(
                competency.SuccessRateCompetencyMeasure.NOT_STARTED,
                skill.score_level)
            assert not skill.proficient

    def test_recommender(self):
        """Test topo skill recommender."""

        self._build_sample_graph()

        # set skill sa score to 1.0 and skill sb score to 0.5
        measure_sa = competency.SuccessRateCompetencyMeasure.load(
            self.user_id, self.sa.id)
        measure_sa.add_score(1.0)
        measure_sa.save()
        measure_sb = competency.SuccessRateCompetencyMeasure.load(
            self.user_id, self.sb.id)
        measure_sb.add_score(0.0)
        measure_sb.add_score(1.0)
        measure_sb.save()

        # verify that the proficient skill list equals [sa]
        # verify that the recommended skill list equals [sb, sc]
        skill_map = SkillMap.load(self.course, self.user_id)
        recommender = SkillRecommender.instance(skill_map)
        recommended, learned = recommender.recommend()
        self.assertEqual(1, len(learned))
        self.assertEqual(2, len(recommended))
        self.assertEqual(self.sb.id, recommended[0].id)
        self.assertEqual(self.sc.id, recommended[1].id)
        assert learned[0].competency_measure.last_modified

        # add second successful attempt for skill b and:
        # verify that the proficient skill list equals [sa, sb]
        # verify that the recommended skill list equals [sc, sd]
        measure_sb = competency.SuccessRateCompetencyMeasure.load(
            self.user_id, self.sb.id)
        measure_sb.add_score(1.0)
        assert measure_sb.proficient
        measure_sb.save()
        skill_map = SkillMap.load(self.course, self.user_id)
        recommender = SkillRecommender.instance(skill_map)
        recommended, proficient = recommender.recommend()
        self.assertEqual(2, len(proficient))
        self.assertEqual(2, len(recommended))
        self.assertEqual(self.sc.id, recommended[0].id)
        self.assertEqual(self.sd.id, recommended[1].id)


class SkillMapRdfHandlerTests(BaseSkillMapTests):
    DATA_URL = 'modules/skill_map/rdf/v1/data'
    SCHEMA_URL = '/modules/skill_map/rdf/v1/schema'
    TYPES = [
      'http://localhost%s#skill' % SCHEMA_URL,
      'http://localhost%s#lesson' % SCHEMA_URL,
      'http://localhost%s#question' % SCHEMA_URL,
      ]

    def test_access_rights(self):
        env = {'course': {'browsable': True}}
        with actions.OverriddenEnvironment(env):
            response = self.get(self.SCHEMA_URL)
            self.assertEqual(200, response.status_int)

            response = self.get(self.DATA_URL, expect_errors=True)
            self.assertEqual(200, response.status_int)

        env = {'course': {'browsable': False}}
        with actions.OverriddenEnvironment(env):
            response = self.get(self.SCHEMA_URL)
            self.assertEqual(200, response.status_int)

            response = self.get(self.DATA_URL, expect_errors=True)
            self.assertEqual(401, response.status_int)

    def test_schema(self):
        actions.login(ADMIN_EMAIL)

        response = self.get(self.SCHEMA_URL)
        self.assertEqual(200, response.status_int)
        Graph().parse(data=response.body, format="application/rdf+xml")

    def test_data(self):
        self._build_sample_graph()
        self._create_lessons()

        skill_graph = SkillGraph.load()
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))

        # link a skill to the question
        question = self._create_mc_question('Test question')
        question.dict[SKILLS_KEY] = [skill.id]
        models.QuestionDAO.save(question)

        # links a skill to a lesson
        self.lesson1.properties[SKILLS_KEY] = [skill.id]
        self.course.save()

        actions.login(ADMIN_EMAIL)

        response = self.get(self.DATA_URL)
        self.assertEqual(200, response.status_int)
        Graph().parse(data=response.body, format="application/rdf+xml")

        node_names = ['a', 'b', 'c', 'd', 'e', 'f']

        imports = [
            '<rdf:type ',
            '<rdfs:comment>',
        ]

        literals = [
          '<gcbsm:id ',
          '<gcbsm:prerequisite ',
          ]

        relations = [
          '<gcbsm:taught_in ',
          '<gcbsm:assessed_by ',
          ]

        actions.assert_contains(self.SCHEMA_URL, response.body)
        for name in node_names:
            actions.assert_contains(
                '<rdfs:label>%s</rdfs:label>' % name, response.body)
        for term in literals + relations + imports + self.TYPES:
            actions.assert_contains(term, response.body)


class LocationListRestHandlerTests(BaseSkillMapTests):
    URL = 'rest/modules/skill_map/locations'

    def test_refuses_list_to_non_admin(self):
        response = self.get(self.URL)
        self.assertEqual(200, response.status_int)
        body = transforms.loads(response.body)
        self.assertEqual(401, body['status'])
        self.assertEqual('Access denied.', body['message'])

    def test_get_lessons(self):
        unit = self.course.add_unit()
        unit.title = 'Test Unit'
        lesson1 = self.course.add_lesson(unit)
        lesson1.title = 'Test Lesson 1'
        lesson2 = self.course.add_lesson(unit)
        lesson2.title = 'Test Lesson 2'
        self.course.save()

        actions.login(ADMIN_EMAIL)

        response = self.get(self.URL)
        self.assertEqual(200, response.status_int)
        body = transforms.loads(response.body)
        self.assertEqual(200, body['status'])
        payload = transforms.loads(body['payload'])
        lessons = payload['lessons']

        expected_lessons = [
            {
                'edit_href': 'dashboard?action=edit_lesson&key=2',
                'sort_key': [1, 2],
                'label': '1.1',
                'href': 'unit?unit=1&lesson=2',
                'key': 'lesson:2',
                'description': lesson1.title,
                'lesson_index': 1,
                'lesson_title': 'Test Lesson 1',
                'unit_index': 1,
                'unit_title': 'Test Unit',
                'unit_id': 1
            },
            {
                'edit_href': 'dashboard?action=edit_lesson&key=3',
                'sort_key': [1, 3],
                'label': '1.2',
                'href': 'unit?unit=1&lesson=3',
                'key': 'lesson:3',
                'description': lesson2.title,
                'lesson_index': 2,
                'lesson_title': 'Test Lesson 2',
                'unit_index': 1,
                'unit_title': 'Test Unit',
                'unit_id': 1
            }]
        self.assertEqual(expected_lessons, lessons)


class SkillRestHandlerTests(BaseSkillMapTests):
    URL = 'rest/modules/skill_map/skill'
    XSRF_TOKEN = 'skill-handler'

    def _put(
            self, version=None, name=None, description=None,
            prerequisite_ids=None, xsrf_token=None, key=None,
            lesson_ids=None, question_keys=None):
        payload = {
            'version': version,
            'name': name,
            'description': description}
        if prerequisite_ids:
            payload['prerequisites'] = [
                {'id': pid} for pid in prerequisite_ids]
        if lesson_ids:
            payload['lessons'] = [{'key': 'lesson:%s' % x} for x in lesson_ids]
        if question_keys:
            payload['questions'] = [{'key': x} for x in question_keys]
        request_dict = {
            'key': key,
            'xsrf_token': xsrf_token,
            'payload': transforms.dumps(payload)}
        response = self.put(
            self.URL, {'request': transforms.dumps(request_dict)})
        return transforms.loads(response.body)

    def test_rejected_if_not_authorized(self):
        # Bad XSRF_TOKEN
        response = self._put(
            version='1', name=SKILL_NAME, description=SKILL_DESC,
            xsrf_token='BAD XSRF TOKEN')
        self.assertEqual(403, response['status'])

        # Not logged in
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1', name=SKILL_NAME, description=SKILL_DESC,
            xsrf_token=xsrf_token)
        self.assertEqual(401, response['status'])

        # Not admin
        actions.login('not-an-admin@foo.com')
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1', name=SKILL_NAME, description=SKILL_DESC,
            xsrf_token=xsrf_token)
        self.assertEqual(401, response['status'])

    def test_create_skill(self):
        skill_graph = SkillGraph.load()
        self.assertEqual(0, len(skill_graph.skills))

        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1', name=SKILL_NAME, description=SKILL_DESC,
            xsrf_token=xsrf_token)
        self.assertEqual(200, response['status'])
        self.assertEqual('Saved.', response['message'])

        payload = transforms.loads(response['payload'])
        key = payload['key']

        skill_graph = SkillGraph.load()
        self.assertEqual(1, len(skill_graph.skills))

        skill = skill_graph.get(key)
        self.assertEqual(key, skill.id)
        self.assertEqual(SKILL_NAME, skill.name)
        self.assertEqual(SKILL_DESC, skill.description)

    def test_create_skill_with_question(self):
        question = self._create_mc_question('description')
        skill_graph = SkillGraph.load()
        self.assertEqual(0, len(skill_graph.skills))

        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        question_key = 'question_mc:%s' % question.id
        response = self._put(
            version='1', name=SKILL_NAME, description=SKILL_DESC,
            xsrf_token=xsrf_token, question_keys=[question_key])
        self.assertEqual(200, response['status'])
        self.assertEqual('Saved.', response['message'])
        payload = transforms.loads(response['payload'])
        key = payload['key']

        q = models.QuestionDAO.load(question.id)
        self.assertEqual([key], q.dict[SKILLS_KEY])

    def test_create_skill_with_lesson(self):
        unit = self.course.add_unit()
        unit.title = 'Unit'
        lesson = self.course.add_lesson(unit)
        lesson.title = 'Lesson'
        self.course.save()

        skill_graph = SkillGraph.load()
        self.assertEqual(0, len(skill_graph.skills))

        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1', name=SKILL_NAME, description=SKILL_DESC,
            xsrf_token=xsrf_token, lesson_ids=[lesson.lesson_id])
        self.assertEqual(200, response['status'])
        self.assertEqual('Saved.', response['message'])
        payload = transforms.loads(response['payload'])
        key = payload['key']

        self.course = courses.Course(None, self.app_context)
        lesson = self.course.get_lessons_for_all_units()[0]
        self.assertEqual([key], lesson.properties[SKILLS_KEY])

    def test_update_skill_with_lesson(self):
        unit = self.course.add_unit()
        unit.title = 'Unit'
        lesson = self.course.add_lesson(unit)
        lesson.title = 'Lesson'
        self.course.save()

        skill_graph = SkillGraph.load()
        self.assertEqual(0, len(skill_graph.skills))
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))

        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1',
            name=SKILL_NAME_2,
            description=SKILL_DESC,
            xsrf_token=xsrf_token,
            lesson_ids=[lesson.lesson_id],
            key=skill.id)
        self.assertEqual(200, response['status'])
        self.assertEqual('Saved.', response['message'])
        payload = transforms.loads(response['payload'])
        key = payload['key']

        self.course = courses.Course(None, self.app_context)
        lesson = self.course.get_lessons_for_all_units()[0]
        self.assertEqual([key], lesson.properties[SKILLS_KEY])

        # check that skill.dict is not polluted with extra key-value pairs
        skill_graph = SkillGraph.load()
        updated_skill = skill_graph.skills[0]
        self.assertItemsEqual(
            ['version', 'name', 'description', 'last_modified'],
            updated_skill.dict.keys())

    def test_create_skill_with_prerequisites(self):
        skill_graph = SkillGraph.load()

        src_skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))

        # add skill with one prerequisite
        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1', name=SKILL_NAME_2,
            description=SKILL_DESC_2,
            prerequisite_ids=[src_skill.id],
            xsrf_token=xsrf_token)

        self.assertEqual(200, response['status'])
        self.assertEqual('Saved.', response['message'])
        payload = transforms.loads(response['payload'])

        tgt_key = payload['key']
        skill_graph = SkillGraph.load()
        self.assertEqual(2, len(skill_graph.skills))
        prerequisites = skill_graph.prerequisites(tgt_key)
        self.assertEqual(1, len(prerequisites))
        self.assertEqual(src_skill.id, prerequisites[0].id)

        tgt_skill = payload['skill']
        self.assertEqual(SKILL_NAME_2, tgt_skill['name'])
        self.assertEqual(tgt_skill['description'], SKILL_DESC_2)
        self.assertEqual([], tgt_skill['lessons'])
        self.assertEqual(1, len(tgt_skill['prerequisite_ids']))

    def test_(self):
        skill_graph = SkillGraph.load()

        src_skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        tgt_skill = skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))

        # update prerequisites
        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1',
            name=SKILL_NAME_3,
            description=SKILL_DESC_3,
            prerequisite_ids=[src_skill.id],
            xsrf_token=xsrf_token,
            key=tgt_skill.id)

        self.assertEqual(200, response['status'])
        self.assertEqual('Saved.', response['message'])

        payload = transforms.loads(response['payload'])
        tgt_key = payload['key']

        skill_graph = SkillGraph.load()
        tgt_skill = skill_graph.get(tgt_key)

        self.assertEqual(2, len(skill_graph.skills))
        prerequisites = skill_graph.prerequisites(tgt_key)
        self.assertEqual(1, len(prerequisites))
        self.assertEqual(src_skill.id, prerequisites[0].id)
        self.assertEqual(tgt_skill.name, SKILL_NAME_3)
        self.assertEqual(tgt_skill.description, SKILL_DESC_3)

    def test_reject_update_with_duplicate_names(self):
        skill_graph = SkillGraph.load()
        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))

        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1',
            name=skill_1.name,
            description=SKILL_DESC_2,
            xsrf_token=xsrf_token)

        self.assertEqual(412, response['status'])
        self.assertEqual('Name must be unique', response['message'])
        payload = json.loads(response['payload'])
        assert payload.has_key('messages')
        assert payload['messages'].has_key('skill-name')
        self.assertEqual(1, len(payload['messages']['skill-name']))
        self.assertEqual('Name must be unique',
                         payload['messages']['skill-name'][0])
        skill_graph = skill_graph.load()
        self.assertEqual(1, len(skill_graph.skills))

    def test_reject_update_with_duplicate_prerequisites(self):
        skill_graph = SkillGraph.load()

        src_skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        tgt_skill = skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))

        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1',
            name=SKILL_NAME_3,
            description=SKILL_DESC_3,
            prerequisite_ids=[src_skill.id, src_skill.id],
            xsrf_token=xsrf_token,
            key=tgt_skill.id)

        self.assertEqual(412, response['status'])
        self.assertEqual('Prerequisites must be unique', response['message'])
        payload = json.loads(response['payload'])
        assert payload.has_key('key')
        assert payload['messages'].has_key('skill-prerequisites')
        self.assertEqual(1, len(payload['messages']['skill-prerequisites']))
        self.assertEqual('Prerequisites must be unique',
                         payload['messages']['skill-prerequisites'][0])


    def test_reject_update_prerequisites_with_self_loop(self):
        skill_graph = SkillGraph.load()
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1',
            name=skill.name,
            description=skill.description,
            prerequisite_ids=[skill.id],
            xsrf_token=xsrf_token,
            key=skill.id)

        self.assertEqual(412, response['status'])
        self.assertEqual(
            'A skill cannot be its own prerequisite', response['message'])

        payload = json.loads(response['payload'])
        self.assertEqual(1, len(payload['messages']['skill-prerequisites']))
        self.assertEqual('A skill cannot be its own prerequisite',
                         payload['messages']['skill-prerequisites'][0])


        skill_graph = SkillGraph.load()
        skill = skill_graph.get(skill.id)
        self.assertEqual(set(), skill.prerequisite_ids)

    def test_get_skill(self):
        skill_graph = SkillGraph.load()
        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        actions.login(ADMIN_EMAIL)
        get_url = '%s?%s' % (self.URL, urllib.urlencode({'key': skill_1.id}))
        response = transforms.loads(self.get(get_url).body)
        self.assertEqual(200, response['status'])
        skill = transforms.loads(response['payload'])['skill']
        self.assertEqual(skill_1.id, skill['id'])
        self.assertEqual(skill_1.name, skill['name'])
        self.assertEqual(skill_1.description, skill['description'])

    def test_get_skills(self):
        skill_graph = SkillGraph.load()

        assert skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        assert skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))
        assert skill_graph.add(Skill.build(SKILL_NAME_3, SKILL_DESC_3))

        actions.login(ADMIN_EMAIL)
        response = transforms.loads(self.get(self.URL).body)

        self.assertEqual(200, response['status'])
        self.assertIn('xsrf_token', response)

        skills = transforms.loads(response['payload'])['skills']
        self.assertEqual(3, len(skills))

        # check that every skill has the following properties
        keys = ['id', 'name', 'description', 'prerequisite_ids', 'lessons',
                'questions', 'sort_key', 'topo_sort_key', 'score',
                'score_level', 'successor_ids']
        for skill in skills:
            self.assertItemsEqual(keys, skill.keys())

        # check that skills are sorted in lexicographic order
        skill_names = sorted([SKILL_NAME, SKILL_NAME_2, SKILL_NAME_3])
        self.assertEqual(skill_names, [x['name'] for x in skills])

    def test_get_skills_multiple_lessons(self):
        """The skills are mapped to more than one lesson."""
        skill_graph = SkillGraph.load()

        skill_1 = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        unit = self.course.add_unit()
        unit.title = 'Test Unit'
        lesson1 = self.course.add_lesson(unit)
        lesson1.title = 'Test Lesson 1'
        lesson2 = self.course.add_lesson(unit)
        lesson2.title = 'Test Lesson 2'
        self.course.save()
        lesson1.properties[SKILLS_KEY] = [skill_1.id]
        lesson2.properties[SKILLS_KEY] = [skill_1.id]
        self.course.save()

        actions.login(ADMIN_EMAIL)
        response = transforms.loads(self.get(self.URL).body)
        self.assertEqual(200, response['status'])

        skills = transforms.loads(response['payload'])['skills']
        self.assertEqual(1, len(skills))
        # All lessons listed
        self.assertEqual(2, len(skills[0]['lessons']))

    def test_delete_skill(self):
        skill_graph = SkillGraph.load()
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))

        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        delete_url = '%s?%s' % (
            self.URL,
            urllib.urlencode({
                'key': skill.id,
                'xsrf_token': cgi.escape(xsrf_token)
            }))
        response = self.delete(delete_url)
        self.assertEquals(200, response.status_int)

    def test_delete_skill_with_lesson(self):
        # add a unit and a lesson to the course
        unit = self.course.add_unit()
        unit.title = 'Test Unit'
        lesson = self.course.add_lesson(unit)
        lesson.title = 'Test Lesson'
        self.course.save()

        # add one skill to the lesson
        skill_graph = SkillGraph.load()
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        lesson.properties[SKILLS_KEY] = [skill.id]
        self.course.update_lesson(lesson)
        self.course.save()

        skill_map = SkillMap.load(self.course)
        lessons = skill_map.get_lessons_for_skill(skill)
        self.assertEqual(1, len(lessons))
        self.assertEqual('Test Lesson', lessons[0].title)

        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        delete_url = '%s?%s' % (
            self.URL,
            urllib.urlencode({
                'key': skill.id,
                'xsrf_token': cgi.escape(xsrf_token)
            }))
        response = self.delete(delete_url)

        self.assertEquals(200, response.status_int)
        course = courses.Course(None, self.course.app_context)
        skill_map = SkillMap.load(course)
        lessons = skill_map.get_lessons_for_skill(skill)
        self.assertEqual([], lessons)

    def test_delete_skill_with_question(self):
        # create a question
        description = 'description'
        question = self._create_mc_question(description)

        # link a skill to the question
        skill_graph = SkillGraph.load()
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        question.dict[SKILLS_KEY] = [skill.id]
        models.QuestionDAO.save(question)

        skill_map = SkillMap.load(self.course)
        questions = skill_map.get_questions_for_skill(skill)
        self.assertEqual(1, len(questions))
        self.assertEqual(description, questions[0].description)

        # delete the skill
        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        delete_url = '%s?%s' % (
            self.URL,
            urllib.urlencode({
                'key': skill.id,
                'xsrf_token': cgi.escape(xsrf_token)
            }))
        response = self.delete(delete_url)
        self.assertEquals(200, response.status_int)

        # assert question is not link to the deleted skill
        question = models.QuestionDAO.load(question.id)
        assert (
            SKILLS_KEY not in question.dict or
            not question.dict[SKILLS_KEY])

    def test_get_skill_with_questions(self):
        """Get a skill mapped to two questions."""

        # map a skill to two questions
        skill_graph = SkillGraph.load()
        skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        q1 = self._create_mc_question('description 1')
        q2 = self._create_mc_question('description 2')
        q1.dict[SKILLS_KEY] = [skill.id]
        q2.dict[SKILLS_KEY] = [skill.id]
        models.QuestionDAO.save_all([q1, q2])

        # get skills
        actions.login(ADMIN_EMAIL)
        response = transforms.loads(self.get(self.URL).body)
        self.assertEqual(200, response['status'])
        skills = transforms.loads(response['payload'])['skills']
        self.assertEqual(1, len(skills))

        # assert that it's linked to two questions
        self.assertEqual(2, len(skills[0]['questions']))

    def test_delete_prerequisites(self):
        skill_graph = SkillGraph.load()
        src_skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        tgt_skill = skill_graph.add(Skill.build(SKILL_NAME_2, SKILL_DESC_2))
        skill_graph.add_prerequisite(tgt_skill.id, src_skill.id)
        skill_graph = SkillGraph.load()
        self.assertEqual(1, len(skill_graph.prerequisites(tgt_skill.id)))

        # delete prerequisite
        actions.login(ADMIN_EMAIL)
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(self.XSRF_TOKEN)
        response = self._put(
            version='1',
            name=tgt_skill.name,
            description=tgt_skill.description,
            prerequisite_ids=[],
            xsrf_token=xsrf_token,
            key=tgt_skill.id)

        self.assertEqual(200, response['status'])
        self.assertEqual('Saved.', response['message'])

        skill_graph = SkillGraph.load()
        prerequisites = skill_graph.prerequisites(tgt_skill.id)
        self.assertEqual(0, len(prerequisites))


class SkillMapHandlerTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'skill_map_course'
    SKILL_MAP_URL = 'modules/skill_map?action=edit_skills_table'
    GRAPH_URL = 'modules/skill_map?action=edit_dependency_graph'

    def setUp(self):
        super(SkillMapHandlerTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Skill Map Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, context)
        self.unit = self.course.add_unit()
        self.unit.title = 'Unit 1'
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Lesson 1'
        self.course.save()

        actions.login(self.ADMIN_EMAIL, is_admin=True)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(SkillMapHandlerTests, self).tearDown()

    def test_rejected_if_not_authorized(self):
        actions.login('student@foo.com')
        response = self.get(self.SKILL_MAP_URL)
        self.assertEqual(302, response.status_int)

    def test_dependency_graph_tab(self):
        response = self.get(self.GRAPH_URL)
        self.assertEqual(200, response.status_int)

        dom = self.parse_html_string_to_soup(response.body)

        graph_div = dom.select('.graph')[0]
        assert len(dom.select('.gcb-button-toolbar'))

        # verify that skills is the active tab for the skills graph
        skills_tab = dom.select('a#menu-item__edit__skills_table')[0]
        assert 'gcb-active' in skills_tab.get('class')

    def test_dependency_graph(self):
        skill_graph = SkillGraph.load()
        src_skill = skill_graph.add(Skill.build(SKILL_NAME, SKILL_DESC))
        tgt_skill = skill_graph.add(Skill.build(
            SKILL_NAME_2, SKILL_DESC_2,
            prerequisite_ids=[{'id': src_skill.id}]))

        response = self.get(self.GRAPH_URL)

        self.assertEqual(200, response.status_int)
        dom = self.parse_html_string_to_soup(response.body)

        graph_div = dom.select('.graph')[0]
        assert len(dom.select('.gcb-button-toolbar'))

        nodes = json.loads(graph_div.get('data-nodes'))
        self.assertEqual(2, len(nodes))
        links = json.loads(graph_div.get('data-links'))
        self.assertEqual(1, len(links))
        link = links[0]
        # The link points from the node to its prerequisite
        # because d3 dependo library follows the discrete math convention
        # for arrow direction
        if nodes[0]['id'] == tgt_skill.name:
            self.assertEqual(1, link['source'])
            self.assertEqual(0, link['target'])
        elif nodes[0]['id'] == src_skill.name:
            self.assertEqual(0, link['source'])
            self.assertEqual(1, link['target'])
        else:
            raise Exception('Unexpected skill name.')


class StudentSkillViewWidgetTests(BaseSkillMapTests):

    def setUp(self):
        super(StudentSkillViewWidgetTests, self).setUp()
        actions.login(ADMIN_EMAIL)

        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.unit.availability = courses.AVAILABILITY_AVAILABLE
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Test Lesson'
        self.lesson.availability = courses.AVAILABILITY_AVAILABLE
        self.course.save()

    def _getSkillPanelWidget(self):
        url = 'unit?unit=%(unit)s&lesson=%(lesson)s' % {
            'unit': self.unit.unit_id, 'lesson': self.lesson.lesson_id}
        response = self.get(url)
        dom = self.parse_html_string(response.body)
        self.assertEqual(
            'Test Lesson',
            dom.find('.//h1[@class="gcb-lesson-title"]/span').text.strip())
        return dom.find('.//div[@class="skill-panel"]')

    def test_skills_widget_supressed_by_course_settings(self):
        skill_graph = SkillGraph.load()
        sa = skill_graph.add(Skill.build('a', 'describe a'))
        sb = skill_graph.add(Skill.build('b', 'describe b'))
        self.lesson.properties[SKILLS_KEY] = [sa.id, sb.id]
        self.course.save()

        # Skill widget is not shown if supressed by course setting
        env = {'course': {'display_skill_widget': False}}
        with actions.OverriddenEnvironment(env):
            self.assertIsNone(self._getSkillPanelWidget())

        # But the skill widget *is* shown if the course setting is True or is
        # unset
        self.assertIsNotNone(self._getSkillPanelWidget())

        env = {'course': {'display_skill_widget': True}}
        with actions.OverriddenEnvironment(env):
            self.assertIsNotNone(self._getSkillPanelWidget())

    def test_no_skills_in_lesson(self):
        self.assertIsNone(self._getSkillPanelWidget())

    def test_skills_with_no_prerequisites_or_successors(self):
        # Expect skills shown and friendly messages for prerequ and successors
        skill_graph = SkillGraph.load()
        sa = skill_graph.add(Skill.build('a', 'describe a'))
        sb = skill_graph.add(Skill.build('b', 'describe b'))
        self.lesson.properties[SKILLS_KEY] = [sa.id, sb.id]
        self.course.save()

        widget = self._getSkillPanelWidget()
        skills_div, details_div, control_div = widget.findall('./*')

        actions.assert_contains(
            'Taught in this lesson',
            skills_div.find('./span[@class="section-title"]').text)

        li_list = skills_div.findall('.//li[@class="skill unknown"]')
        self.assertEqual(2, len(li_list))
        actions.assert_contains('a', li_list[0].text)
        actions.assert_contains(
            'describe a', li_list[0].attrib['data-skill-description'])
        actions.assert_contains('b', li_list[1].text)
        actions.assert_contains(
            'describe b', li_list[1].attrib['data-skill-description'])

        details_xml = cElementTree.tostring(details_div)
        actions.assert_contains('doesn\'t have any prerequisites', details_xml)
        actions.assert_contains('isn\'t a prerequisite', details_xml)

    def test_skills_with_prerequisites_and_successors(self):
        # Create skills, a, b, c, d
        # a --> b
        # c --> d
        # Add skills {b, c} to self.lesson
        # Expect self.lesson.depends_on == {a}
        # Expect self.lesson.leads_to == {d}
        skill_graph = SkillGraph.load()
        sa = skill_graph.add(Skill.build('a', 'describe a'))
        sb = skill_graph.add(Skill.build('b', 'describe b'))
        sc = skill_graph.add(Skill.build('c', 'describe c'))
        sd = skill_graph.add(Skill.build('d', 'describe d'))

        skill_graph.add_prerequisite(sb.id, sa.id)
        skill_graph.add_prerequisite(sd.id, sc.id)

        self.lesson.properties[SKILLS_KEY] = [sb.id, sc.id]
        self.course.save()

        widget = self._getSkillPanelWidget()

        # Check that 'b' and 'c' are listed as skills in this lesson
        skills_in_lesson = widget.findall(
            './div[1]//li[@class="skill unknown"]')
        self.assertEqual(2, len(skills_in_lesson))
        actions.assert_contains('b', skills_in_lesson[0].text)
        actions.assert_contains('c', skills_in_lesson[1].text)

        # Skill 'a' is in depends_on
        depends_on = widget.findall('./div[2]/div[1]/ol/li')
        self.assertEqual(1, len(depends_on))
        self.assertEqual(str(sa.id), depends_on[0].attrib['data-skill-id'])

        # Skill 'd' is in leads_to'
        leads_to = widget.findall('./div[2]/div[2]/ol/li')
        self.assertEqual(1, len(leads_to))
        self.assertEqual(str(sd.id), leads_to[0].attrib['data-skill-id'])

        # Add skill 'a' to the lesson and check that is not in depends_on
        self.lesson.properties[SKILLS_KEY].append(sa.id)
        self.course.save()
        widget = self._getSkillPanelWidget()
        depends_on = widget.findall('./div[2]/div[1]/ol/li')
        self.assertEqual(0, len(depends_on))

        # In fact even if 'a' is also taught elsewhere, because it's taught
        # in this lesson, don't list it.
        other_lesson = self.course.add_lesson(self.unit)
        other_lesson.title = 'Other Lesson'
        other_lesson.availability = courses.AVAILABILITY_AVAILABLE
        other_lesson.properties[SKILLS_KEY] = [sa.id]
        self.course.save()
        widget = self._getSkillPanelWidget()
        depends_on = widget.findall('./div[2]/div[1]/ol/li')
        self.assertEqual(0, len(depends_on))

    def test_skill_with_multiple_follow_ons(self):
        # Set up one skill which is a prerequisite of two skills and expect it
        # to be shown only once in depends_on"
        skill_graph = SkillGraph.load()
        sa = skill_graph.add(Skill.build('a', 'common prerequisite'))
        sb = skill_graph.add(Skill.build('b', 'depends on a'))
        sc = skill_graph.add(Skill.build('c', 'also depends on a'))

        skill_graph.add_prerequisite(sb.id, sa.id)
        skill_graph.add_prerequisite(sc.id, sa.id)

        self.lesson.properties[SKILLS_KEY] = [sb.id, sc.id]
        self.course.save()

        widget = self._getSkillPanelWidget()

        # Check B and C are listed as skills in this lesson
        skills_in_lesson = widget.findall(
            './div[1]//li[@class="skill unknown"]')
        self.assertEqual(2, len(skills_in_lesson))
        actions.assert_contains('b', skills_in_lesson[0].text)
        actions.assert_contains('c', skills_in_lesson[1].text)

        # Skill A is listed exactly once in the "depends on" section
        depends_on = widget.findall('./div[2]/div[1]/ol/li')
        self.assertEqual(1, len(depends_on))
        self.assertEqual(str(sa.id), depends_on[0].attrib['data-skill-id'])

    def test_skills_cards_have_title_description_and_lesson_links(self):
        # The lesson contains Skill A which has Skill B as a follow-on. Skill B
        # is found in Lesson 2. Check that the skill card shown for Skill B in
        # Lesson 1 has correct information
        skill_graph = SkillGraph.load()
        sa = skill_graph.add(Skill.build('a', 'describe a'))
        sb = skill_graph.add(Skill.build('b', 'describe b'))
        skill_graph.add_prerequisite(sb.id, sa.id)

        self.lesson.properties[SKILLS_KEY] = [sa.id]
        lesson2 = self.course.add_lesson(self.unit)
        lesson2.title = 'Test Lesson 2'
        lesson2.availability = courses.AVAILABILITY_AVAILABLE
        lesson2.properties[SKILLS_KEY] = [sb.id]
        self.course.save()

        widget = self._getSkillPanelWidget()
        leads_to = widget.findall('./div[2]/div[2]/ol/li')
        self.assertEqual(1, len(leads_to))
        card = leads_to[0]
        name = card.find('.//div[@class="name unknown"]').text
        description = card.find(
            './/div[@class="description"]/div[@class="content"]').text
        locations = card.findall('.//ol[@class="locations"]/li/a')
        self.assertEqual('b', name.strip())
        self.assertEqual('describe b', description.strip())
        self.assertEqual(1, len(locations))
        self.assertEqual(
            '1.2 Test Lesson 2', ' '.join(locations[0].text.strip().split()))
        self.assertEqual(
            'unit?unit=%(unit)s&lesson=%(lesson)s' % {
                'unit': self.unit.unit_id, 'lesson': lesson2.lesson_id},
            locations[0].attrib['href'])

        # Next, make the lesson unavailable
        lesson2.availability = courses.AVAILABILITY_UNAVAILABLE
        self.course.save()

        # Except the subsequent skill does not show its lesson
        widget = self._getSkillPanelWidget()
        leads_to = widget.findall('./div[2]/div[2]/ol/li')
        card = leads_to[0]
        locations = card.findall('.//ol[@class="locations"]/li')
        self.assertEqual(1, len(locations))
        self.assertEqual('Not taught', locations[0].text)


class SkillMapAnalyticsTabTests(BaseSkillMapTests):
    """Tests the handlers for the tab Analytics > Skill Map"""
    TAB_URL = ('/{}/dashboard?action=analytics_skill_map'.format(
        COURSE_NAME))
    NON_ADMIN_EMAIL = 'noadmin@example.tests'

    def test_get_tab(self):
        """Performs a get call to the tab."""
        actions.login(ADMIN_EMAIL, is_admin=True)
        response = self.get(self.TAB_URL)
        self.assertEqual(response.status_code, 200)

    def test_get_tab_no_admin(self):
        """Non admin users should not have access."""
        actions.login(self.NON_ADMIN_EMAIL, is_admin=False)
        response = self.get(self.TAB_URL, expect_errors=True)
        self.assertEquals(302, response.status_int)


class GenerateCompetencyHistogramsTests(BaseSkillMapTests):
    """Tests the result of the map reduce job CountSkillCompetencies."""

    def setUp(self):
        super(GenerateCompetencyHistogramsTests, self).setUp()

        # create three success rate measures
        # student-11:skill-1:competency:1
        measure1 = competency.SuccessRateCompetencyMeasure.load(11, 1)
        measure1.add_score(1.0)
        measure1.save()

        # student-11:skill-2:competency:0.5
        measure2 = competency.SuccessRateCompetencyMeasure.load(11, 2)
        measure2.add_score(0.0)
        measure2.add_score(1.0)
        measure2.save()

        # student-22:skill-1:competency:0
        measure3 = competency.SuccessRateCompetencyMeasure.load(22, 1)
        measure3.add_score(0.0)
        measure3.save()

        actions.login(ADMIN_EMAIL, is_admin=True)

    def run_map_reduce_job(self):
        job = competency.GenerateSkillCompetencyHistograms(self.app_context)
        job.submit()
        self.execute_all_deferred_tasks()

    def test_map_reduce_job_output(self):
        self.run_map_reduce_job()
        job = competency.GenerateSkillCompetencyHistograms(
            self.app_context).load()
        job_result = sorted(
            jobs.MapReduceJob.get_results(job), key=lambda x: x[0])
        expected = [
            [1, {'low-competency': 1, 'med-competency': 0, 'high-competency': 1,
                 'avg': 0.5}],
            [2, {'low-competency': 0, 'med-competency': 1, 'high-competency': 0,
                 'avg': 0.5}]]
        self.assertEqual(expected, sorted(job_result))


class CountSkillCompletionsTests(BaseSkillMapTests):
    """Tests the result of the map reduce job CountSkillCompletions."""

    def setUp(self):
        super(CountSkillCompletionsTests, self).setUp()
        actions.login(ADMIN_EMAIL, is_admin=True)
        self._create_skills()
        self._create_students()

    def _create_students(self):
        """Creates 4 StudentPropertyEntities with partial progress."""
        def mktime(str_date):
            return time.mktime(time.strptime(
                str_date, CountSkillCompletion.DATE_FORMAT))
        self.day1 = '2015-01-01'
        self.day2 = '2015-01-02'
        self.day3 = '2015-01-03'
        self.day4 = '2015-01-04'
        c = SkillCompletionTracker.COMPLETED
        p = SkillCompletionTracker.IN_PROGRESS
        # progress string for students
        students_progress = [
            {self.skill1.id : {c: mktime(self.day2), p: mktime(self.day1)},
             self.skill2.id : {c: mktime(self.day4), p: mktime(self.day1)}},
            {self.skill1.id : {c: mktime(self.day2), p: mktime(self.day2)},
             self.skill2.id : {p: mktime(self.day1)}},
            {self.skill1.id : {c: mktime(self.day1)}},
            {}  # No progress
        ]
        for index, progress in enumerate(students_progress):
            student = models.Student(user_id=str(index))
            student.put()
            comp = models.StudentPropertyEntity.create(
                student=student,
                property_name=SkillCompletionTracker.PROPERTY_KEY)
            comp.value = transforms.dumps(progress)
            comp.put()

    def _create_skills(self):
        """Creates 3 skills."""
        skill_graph = SkillGraph.load()
        self.skill1 = skill_graph.add(Skill.build('a', ''))
        self.skill2 = skill_graph.add(Skill.build('b', ''))
        self.skill3 = skill_graph.add(Skill.build('c', ''))
        self.course.save()

    def run_generator_job(self):
        job = CountSkillCompletion(self.app_context)
        job.submit()
        self.execute_all_deferred_tasks()

    def test_job_aggregate_entities(self):
        """Tests the SkillCompletionAggregate entities created by the job."""
        # This is testing:
        #   - Skills completed without in progress state
        #   - Days with no progress
        #   - Skills with no progress
        #   - Students with no progress
        self.run_generator_job()
        job = CountSkillCompletion(self.app_context).load()
        expected = {
            str(self.skill1.id): {self.day1: 1, self.day2: 3},
            str(self.skill2.id): {self.day4: 1},
            str(self.skill3.id): {}
        }
        # Check entities
        result = list(SkillCompletionAggregate.all().run())
        self.assertEqual(3, len(result))  # One per skill
        for aggregate in result:
            skill_id = aggregate.key().name()
            self.assertEqual(expected[skill_id],
                             transforms.loads(aggregate.aggregate))

    def test_job_output(self):
        """Tests the output of the job for the SkillMapDataSource."""
        self.run_generator_job()
        job = CountSkillCompletion(self.app_context).load()
        output = jobs.MapReduceJob.get_results(job)
        expected = [[str(self.skill1.id), 3, 0],
                    [str(self.skill2.id), 1, 1],
                    [str(self.skill3.id), 0, 0]]
        self.assertEqual(sorted(expected), sorted(output))

        template_values = {}
        SkillMapDataSource.fill_values(self.app_context, template_values, job)
        self.assertEqual(transforms.loads(template_values['counts']), [
            [self.skill1.name, 3, 0],
            [self.skill2.name, 1, 1],
            [self.skill3.name, 0, 0]])

    def test_build_additional_mapper_params(self):
        """The additional param in a dictionary mapping from skills to lessons.
        """
        job = CountSkillCompletion(self.app_context)
        result = job.build_additional_mapper_params(self.app_context)
        self.assertEqual(
            {'skill_ids': [self.skill1.id, self.skill2.id, self.skill3.id]},
            result)


class SkillAggregateRestHandlerTests(BaseSkillMapTests):
    """Tests for the class SkillAggregateRestHandler."""

    URL = 'rest/modules/skill_map/skill_aggregate_count'
    XSRF_TOKEN = 'skill_aggregate'

    def _add_aggregates(self):
        self.day1 = '2015-01-01'
        self.day2 = '2015-01-02'
        self.day3 = '2015-01-03'
        self.day4 = '2015-01-04'
        self.skill_ids = range(1, 4)
        self.aggregates = {
            self.skill_ids[0]: {self.day1: 1, self.day2: 2},
            self.skill_ids[1]: {self.day4: 1},
            self.skill_ids[2]: {},
        }
        for skill_id, aggregate in self.aggregates.iteritems():
            SkillCompletionAggregate(
                key_name=str(skill_id),
                aggregate=transforms.dumps(aggregate)).put()

    def test_rejected_if_not_authorized(self):
        # Not logged in
        response = transforms.loads(self.get(self.URL).body)
        self.assertEqual(401, response['status'])

        # logged in but not admin
        actions.login('user@foo.com')
        response = transforms.loads(self.get(self.URL).body)
        self.assertEqual(401, response['status'])

        # logged in as admin
        actions.logout()
        actions.login(ADMIN_EMAIL)
        response = transforms.loads(self.get(self.URL).body)
        self.assertEqual(200, response['status'])

    def test_single_skill_request(self):
        """Asks for one skill information."""
        self._add_aggregates()
        actions.login(ADMIN_EMAIL)
        get_url = '%s?%s' % (self.URL, urllib.urlencode({
            'ids': [self.skill_ids[0]]}, True))

        response = self.get(get_url)
        self.assertEqual(200, response.status_int)
        payload = transforms.loads(response.body)['payload']

        expected_header = ['Date', str(self.skill_ids[0])]
        expected_data = [[self.day1, 1], [self.day2, 2]]
        result = transforms.loads(payload)
        self.assertEqual(expected_header, result['column_headers'])
        self.assertEqual(len(expected_data), len(result['data']))
        for row in expected_data:
            self.assertIn(row, result['data'])

    def test_multiple_skill_request(self):
        """Asks for more than one skill information."""
        self._add_aggregates()
        actions.login(ADMIN_EMAIL)
        get_url = '%s?%s' % (self.URL, urllib.urlencode({
            'ids': self.skill_ids}, True))

        response = self.get(get_url)
        self.assertEqual(200, response.status_int)
        payload = transforms.loads(response.body)['payload']
        result = transforms.loads(payload)

        expected_header = ['Date'] + [str(skill_id)
                                      for skill_id in self.skill_ids]
        expected_data = [
            [self.day1, 1, 0, 0], [self.day2, 2, 0, 0], [self.day4, 2, 1, 0]
        ]
        self.assertEqual(expected_header, result['column_headers'])
        self.assertEqual(len(expected_data), len(result['data']))
        for row in expected_data:
            self.assertIn(row, result['data'])

    def test_no_skill_request(self):
        """Sends a request with no skills."""
        actions.login(ADMIN_EMAIL)

        response = self.get(self.URL)
        self.assertEqual(200, response.status_int)
        payload = transforms.loads(response.body)['payload']
        result = transforms.loads(payload)

        self.assertEqual(['Date'], result['column_headers'])
        self.assertEqual([], result['data'])

    def test_no_skill_aggregate(self):
        """Sends a request with a skill that does not have an object in db."""
        actions.login(ADMIN_EMAIL)

        get_url = '%s?%s' % (self.URL, urllib.urlencode({
            'ids': [1]}, True))
        response = self.get(get_url)
        self.assertEqual(200, response.status_int)
        payload = transforms.loads(response.body)['payload']
        result = transforms.loads(payload)

        self.assertEqual(['Date'], result['column_headers'])
        self.assertEqual([], result['data'])

    def test_exceed_limit_request(self):
        """Exceeds the limit in the number of skills requested."""
        actions.login(ADMIN_EMAIL)
        ids_list = list(range(SkillAggregateRestHandler.MAX_REQUEST_SIZE))
        get_url = '%s?%s' % (self.URL, urllib.urlencode({
            'ids': ids_list}, True))

        response = transforms.loads(self.get(get_url).body)
        self.assertEqual(412, response['status'])


class SkillMapMetricTests(BaseSkillMapTests):
    """Tests for the functions in file skill_map_metrics"""

    def test_nxgraph(self):
        """The graph of SkillMapMetrics and the skill_map are equivalent."""
        self._build_sample_graph()
        # Adding singleton
        sg = self.skill_graph.add(Skill.build('g', ''))
        skill_map = SkillMap.load(self.course)
        nxgraph = SkillMapMetrics(skill_map).nxgraph
        self.assertIsInstance(nxgraph, DiGraph)
        successors = skill_map.build_successors()
        # Check nodes
        self.assertEqual(len(nxgraph), len(successors))
        for skill in successors:
            self.assertIn(skill, nxgraph.nodes(),
                          msg='Node {} not found in nx graph.'.format(skill))
        # Check edges
        original_edges = sum(len(dst) for dst in successors.values())
        self.assertEqual(len(nxgraph.edges()), original_edges)
        for src, dst in nxgraph.edges_iter():
            self.assertIn(src, successors)
            self.assertIn(dst, successors[src],
                          msg='Extra {},{} edge in nx graph.'.format(src, dst))

    def test_find_cycles_no_cycle(self):
        """The input is a directed graph with no cycles. Expected []."""
        self._build_sample_graph()
        skill_map = SkillMap.load(self.course)
        self.assertEqual(SkillMapMetrics(skill_map).simple_cycles(), [])

    def test_find_cycles_one_cycle(self):
        """The input is a directed graph with only 1 cycle."""
        self._build_sample_graph()
        # Adding cycle a -> d -> a
        self.skill_graph.add_prerequisite(self.sa.id, self.sd.id)
        skill_map = SkillMap.load(self.course)
        self.assertEqual(6, len(skill_map.skills()))
        successors = skill_map.build_successors()
        self.assertEqual(
            sorted(SkillMapMetrics(skill_map).simple_cycles()[0]),
            [self.sa.id, self.sd.id])

    def test_find_cycles_multiple_cycles(self):
        """The input is a directed graph with two cycles."""
        self._build_sample_graph()
        # Adding cycle a -> d -> a
        self.skill_graph.add_prerequisite(self.sa.id, self.sd.id)
        # Adding cycle g -> h -> g
        sg = self.skill_graph.add(Skill.build('g', ''))
        sh = self.skill_graph.add(Skill.build('h', ''))
        self.skill_graph.add_prerequisite(sg.id, sh.id)
        self.skill_graph.add_prerequisite(sh.id, sg.id)

        expected = [[self.sa.id, self.sd.id], [sg.id, sh.id]]
        skill_map = SkillMap.load(self.course)
        successors = skill_map.build_successors()
        result = SkillMapMetrics(skill_map).simple_cycles()
        self.assertEqual(len(result), len(expected))
        for cycle in result:
            self.assertIn(sorted(cycle), expected)

    def test_find_cycles_not_conected(self):
        """The input is a directed graph whith an isolated scc."""
        self._build_sample_graph()
        # Adding cycle g -> h -> g
        sg = self.skill_graph.add(Skill.build('g', ''))
        sh = self.skill_graph.add(Skill.build('h', ''))
        self.skill_graph.add_prerequisite(sg.id, sh.id)
        self.skill_graph.add_prerequisite(sh.id, sg.id)
        skill_map = SkillMap.load(self.course)
        expected0 = [sg.id, sh.id]
        successors = skill_map.build_successors()
        result = SkillMapMetrics(skill_map).simple_cycles()
        self.assertEqual(sorted(result[0]), expected0)

    def test_metrics_empty(self):
        """The input is an empty graph."""
        skill_map = SkillMap.load(self.course)
        sm_metrics = SkillMapMetrics(skill_map)
        self.assertEqual(sm_metrics.simple_cycles(), [])
        self.assertEqual(sm_metrics.singletons(), [])
        self.assertEqual(sm_metrics.long_chains(), [])
        expected = {'cycles': [], 'singletons': [], 'long_chains': []}
        self.assertEqual(sm_metrics.diagnose(), expected)

    def test_find_singletons(self):
        """Singletons are components with only one node."""
        self._build_sample_graph()
        # Adding singletons
        sg = self.skill_graph.add(Skill.build('g', ''))
        sh = self.skill_graph.add(Skill.build('h', ''))
        skill_map = SkillMap.load(self.course)
        result = SkillMapMetrics(skill_map).singletons()
        expected = [sg.id, sh.id]
        self.assertEqual(sorted(expected), sorted(result))

    def test_find_long_chains(self):
        """Find all simple paths longer than a constant."""
        # a --> d --> j      g     h --> i
        # b _/                     c --> e --> f
        self._build_sample_graph()
        # Adding singleton
        sg = self.skill_graph.add(Skill.build('g', ''))
        # Adding short path
        sh = self.skill_graph.add(Skill.build('h', ''))
        si = self.skill_graph.add(Skill.build('i', ''))
        self.skill_graph.add_prerequisite(si.id, sh.id)
        # Making path longer
        sj = self.skill_graph.add(Skill.build('j', ''))
        self.skill_graph.add_prerequisite(sj.id, self.sd.id)
        skill_map = SkillMap.load(self.course)
        result = SkillMapMetrics(skill_map).long_chains(2)
        expected = [
            [self.sa.id, self.sd.id, sj.id],
            [self.sb.id, self.sd.id, sj.id],
            [self.sc.id, self.se.id, self.sf.id]
        ]
        self.assertEqual(sorted(expected), sorted(result))

    def test_find_long_chains_multiple(self):
        """Finds longest path when there is more than one path from A to B.
        """
        # a -> b -> c -> ... x
        #  \________________/
        self.skill_graph = SkillGraph.load()
        old_skill = self.skill_graph.add(Skill.build('o', ''))
        last_skill = self.skill_graph.add(Skill.build('l', ''))
        self.skill_graph.add_prerequisite(last_skill.id, old_skill.id)
        chain_ids = [old_skill.id]
        for index in range(CHAINS_MIN_LENGTH):
            new_skill = self.skill_graph.add(Skill.build(str(index), ''))
            chain_ids.append(new_skill.id)
            self.skill_graph.add_prerequisite(new_skill.id, old_skill.id)
            old_skill = new_skill
        self.skill_graph.add_prerequisite(old_skill.id, last_skill.id)
        skill_map = SkillMap.load(self.course)
        result = SkillMapMetrics(skill_map).long_chains()
        self.assertEqual([chain_ids], result)

    def test_get_diagnose(self):
        """Checks the diagnose contains the required metrics.

        The function returns a dictionary with the simple cycles, singletons
        and long_chains.
        """
        self._build_sample_graph()
        # Adding cycle a -> d -> a
        self.skill_graph.add_prerequisite(self.sa.id, self.sd.id)
        # Adding singleton
        sg = self.skill_graph.add(Skill.build('g', ''))
        skill_map = SkillMap.load(self.course)
        result = SkillMapMetrics(skill_map).diagnose()
        expected = {
            'cycles': [[self.sd.id, self.sa.id]],
            'singletons': [sg.id],
            'long_chains': []
        }
        self.assertEqual(result, expected)


class SkillI18nTests(actions.TestBase):
    ADMIN_EMAIL = 'admin@foo.com'
    COURSE_NAME = 'skill_map_course'
    SKILL_MAP_URL = 'modules/skill_map?action=skill_map_skills_table'

    def setUp(self):
        super(SkillI18nTests, self).setUp()

        self.base = '/' + self.COURSE_NAME
        self.app_context = actions.simple_add_course(
            self.COURSE_NAME, self.ADMIN_EMAIL, 'Skill Map Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % self.COURSE_NAME)

        self.course = courses.Course(None, self.app_context)
        self.unit = self.course.add_unit()
        self.unit.title = 'Unit 1'
        self.lesson = self.course.add_lesson(self.unit)
        self.lesson.title = 'Lesson 1'
        self.course.save()

        actions.login(self.ADMIN_EMAIL, is_admin=True)
        actions.update_course_config(self.COURSE_NAME, {
            'extra_locales': [
                {'locale': 'el', 'availability': 'available'},
                {'locale': 'ru', 'availability': 'available'}]
            })
        self.setSkillWidgetSetting(on=True)

    def tearDown(self):
        self.setSkillWidgetSetting(on=False)
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        courses.Course.ENVIRON_TEST_OVERRIDES.clear()
        super(SkillI18nTests, self).tearDown()

    def setSkillWidgetSetting(self, on=True):
        settings = self.course.get_environ(self.app_context)
        settings['course']['display_skill_widget'] = on
        self.course.save_settings(settings)

    def _put_payload(self, url, xsrf_name, key, payload):
        request_dict = {
            'key': key,
            'xsrf_token': (
                crypto.XsrfTokenManager.create_xsrf_token(xsrf_name)),
            'payload': transforms.dumps(payload)
        }
        response = transforms.loads(self.put(
            url, {'request': transforms.dumps(request_dict)}).body)
        self.assertEquals(200, response['status'])
        self.assertEquals('Saved.', response['message'])
        return response

    def _assert_progress(self, key, el_progress=None, ru_progress=None):
        progress_dto = i18n_dashboard.I18nProgressDAO.load(str(key))
        self.assertIsNotNone(progress_dto)
        self.assertEquals(el_progress, progress_dto.get_progress('el'))
        self.assertEquals(ru_progress, progress_dto.get_progress('ru'))

    def test_on_skill_changed(self):
        # Make a skill with a weird name and weird description.
        skill = Skill(None, {
            'name': 'x',
            'description': 'y'
            })
        skill_key = _SkillDao.save(skill)
        key = resource.Key(ResourceSkill.TYPE, skill_key)

        # Make a resource bundle corresponding to the skill, but with a
        # translation of the skill's description not matching the name
        # or description.
        bundle_key = i18n_dashboard.ResourceBundleKey.from_resource_key(
            key, 'el')
        bundle = i18n_dashboard.ResourceBundleDTO(str(bundle_key), {
            'name': {
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': SKILL_NAME,
                    'target_value': SKILL_NAME.upper(),
                    }]
                },
            'description': {
                'type': 'text',
                'source_value': '',
                'data': [{
                    'source_value': SKILL_DESC,
                    'target_value': SKILL_DESC.upper(),
                    }]
                },
            })
        i18n_dashboard.ResourceBundleDAO.save(bundle)

        # Now, call the REST url to update the skill's name and description
        # to be something matching the current translated version.  We should
        # now believe that the translation is current and up-to date.
        self._put_payload(
            'rest/modules/skill_map/skill',
            SkillRestHandler.XSRF_TOKEN,
            skill_key,
            {
                'version': SkillRestHandler.SCHEMA_VERSIONS[0],
                'name': SKILL_NAME,
                'description': SKILL_DESC,
            })
        self.execute_all_deferred_tasks()
        self._assert_progress(
            key,
            el_progress=i18n_dashboard.I18nProgressDTO.DONE,
            ru_progress=i18n_dashboard.I18nProgressDTO.NOT_STARTED)

        # Again using the REST interface, change the native-language
        # description to something else.  The translation should show as
        # being in-progress (we have something), but not up-to-date.
        self._put_payload(
            'rest/modules/skill_map/skill',
            SkillRestHandler.XSRF_TOKEN,
            skill_key,
            {
                'version': SkillRestHandler.SCHEMA_VERSIONS[0],
                'name': SKILL_NAME,
                'description': SKILL_DESC_2,
            })

        self.execute_all_deferred_tasks()
        self._assert_progress(
            key,
            el_progress=i18n_dashboard.I18nProgressDTO.IN_PROGRESS,
            ru_progress=i18n_dashboard.I18nProgressDTO.NOT_STARTED)

    def test_skills_are_translated(self):
        skill = Skill(None, {
            'name': SKILL_NAME,
            'description': SKILL_DESC
            })
        skill_key = _SkillDao.save(skill)
        key = resource.Key(ResourceSkill.TYPE, skill_key)
        bundle_key = i18n_dashboard.ResourceBundleKey.from_resource_key(
            key, 'el')
        bundle = i18n_dashboard.ResourceBundleDTO(str(bundle_key), {
            'name': {
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': SKILL_NAME,
                    'target_value': SKILL_NAME.upper(),
                    }]
                },
            'description': {
                'type': 'text',
                'source_value': '',
                'data': [{
                    'source_value': SKILL_DESC,
                    'target_value': SKILL_DESC.upper(),
                    }]
                },
            })
        i18n_dashboard.ResourceBundleDAO.save(bundle)
        self.lesson.properties[SKILLS_KEY] = [skill_key]
        self.course.save()

        # Verify that we get the untranslated (lowercased) version when we
        # do not want to see the translated language.
        response = self.get('unit?unit=%s&lesson=%s' %
                (self.unit.unit_id, self.lesson.lesson_id))
        dom = self.parse_html_string(response.body)
        skill_li = dom.find('.//li[@data-skill-description="%s"]' %
                            skill.description)
        skill_text = (''.join(skill_li.itertext())).strip()
        self.assertEqual(skill.name, skill_text)

        # Set pref to see translated version
        prefs = models.StudentPreferencesDAO.load_or_default()
        prefs.locale = 'el'
        models.StudentPreferencesDAO.save(prefs)

        # And verify that we do get the translated (uppercase) version.
        response = self.get('unit?unit=%s&lesson=%s' %
                 (self.unit.unit_id, self.lesson.lesson_id))
        dom = self.parse_html_string(response.body)
        skill_li = dom.find('.//li[@data-skill-description="%s"]' %
                            skill.description.upper())
        skill_text = (''.join(skill_li.itertext())).strip()
        self.assertEqual(skill.name.upper(), skill_text)

        # Verify that one-off title translation also works.
        try:
            sites.set_path_info('/' + self.COURSE_NAME)
            ctx = sites.get_course_for_current_request()
            save_locale = ctx.get_current_locale()

            # Untranslated
            ctx.set_current_locale(None)
            i18n_title = str(TranslatableResourceSkill.get_i18n_title(key))
            self.assertEquals(SKILL_NAME, i18n_title)

            # Translated
            ctx.set_current_locale('el')
            i18n_title = str(TranslatableResourceSkill.get_i18n_title(key))
            self.assertEquals(SKILL_NAME.upper(), i18n_title)
        finally:
            ctx.set_current_locale(save_locale)
            sites.unset_path_info()

    def test_skills_appear_on_i18n_dashboard(self):
        skill = Skill(None, {
            'name': SKILL_NAME,
            'description': SKILL_DESC
            })
        _SkillDao.save(skill)
        skill = Skill(None, {
            'name': SKILL_NAME_2,
            'description': SKILL_DESC_2
            })
        _SkillDao.save(skill)
        response = self.get('dashboard?action=i18n_dashboard')
        soup = self.parse_html_string_to_soup(response.body)
        skills_table = soup.select('[data-title="Skills"]')[0]
        name_cells = skills_table.select('tbody .name')
        self.assertEqual(
            name_cells[0].text.strip(), SKILL_NAME_2,
            'Skill name 2 added second appears first due to sorting')
        self.assertEqual(
            name_cells[1].text.strip(), SKILL_NAME,
            'Skill name added first appears second due to sorting')

    def _do_upload(self, contents):
        xsrf_token = crypto.XsrfTokenManager.create_xsrf_token(
            i18n_dashboard.TranslationUploadRestHandler.XSRF_TOKEN_NAME)
        response = self.post(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationUploadRestHandler.URL),
            {'request': transforms.dumps({'xsrf_token': xsrf_token})},
            upload_files=[('file', 'doesntmatter', contents)])
        return response

    def _do_download(self, payload):
        request = {
            'xsrf_token': crypto.XsrfTokenManager.create_xsrf_token(
                i18n_dashboard.TranslationDownloadRestHandler.XSRF_TOKEN_NAME),
            'payload': transforms.dumps(payload),
            }
        response = self.post(
            '/%s%s' % (self.COURSE_NAME,
                       i18n_dashboard.TranslationDownloadRestHandler.URL),
            {'request': transforms.dumps(request)})
        return response

    def _parse_zip_response(self, response):
        download_zf = zipfile.ZipFile(cStringIO.StringIO(response.body), 'r')
        out_stream = StringIO.StringIO()
        out_stream.fp = out_stream
        for item in download_zf.infolist():
            file_data = download_zf.read(item)
            catalog = pofile.read_po(cStringIO.StringIO(file_data))
            yield catalog

    def test_export_skills(self):
        skill = Skill(None, {
            'name': SKILL_NAME,
            'description': SKILL_DESC
            })
        skill_key = _SkillDao.save(skill)
        key = resource.Key(ResourceSkill.TYPE, skill_key)
        bundle_key = i18n_dashboard.ResourceBundleKey.from_resource_key(
            key, 'el')
        bundle = i18n_dashboard.ResourceBundleDTO(str(bundle_key), {
            'name': {
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': SKILL_NAME,
                    'target_value': SKILL_NAME.upper(),
                    }]
                },
            'description': {
                'type': 'text',
                'source_value': '',
                'data': [{
                    'source_value': SKILL_DESC,
                    'target_value': SKILL_DESC.upper(),
                    }]
                },
            })
        i18n_dashboard.ResourceBundleDAO.save(bundle)

        response = self._do_download({
            'locales': [{'locale': 'el', 'checked': True}],
            'export_what': 'all',
            })

        found_skill_name = False
        found_skill_desc = False
        for catalog in self._parse_zip_response(response):
            for msg in catalog:
                if msg.id == SKILL_NAME:
                    self.assertEquals(SKILL_NAME.upper(), msg.string)
                    found_skill_name = True
                if msg.id == SKILL_DESC:
                    self.assertEquals(SKILL_DESC.upper(), msg.string)
                    found_skill_desc = True
        self.assertTrue(found_skill_name)
        self.assertTrue(found_skill_desc)

    def test_import_skills(self):
        skill = Skill(None, {
            'name': SKILL_NAME,
            'description': SKILL_DESC
            })
        skill_key = _SkillDao.save(skill)
        key = resource.Key(ResourceSkill.TYPE, skill_key)
        bundle_key = i18n_dashboard.ResourceBundleKey.from_resource_key(
            key, 'el')
        bundle = i18n_dashboard.ResourceBundleDTO(str(bundle_key), {
            'name': {
                'type': 'string',
                'source_value': '',
                'data': [{
                    'source_value': SKILL_NAME,
                    'target_value': SKILL_NAME.upper(),
                    }]
                },
            'description': {
                'type': 'text',
                'source_value': '',
                'data': [{
                    'source_value': SKILL_DESC,
                    'target_value': SKILL_DESC.upper(),
                    }]
                },
            })
        i18n_dashboard.ResourceBundleDAO.save(bundle)

        # Do download to force creation of progress entities.
        self._do_download({
            'locales': [{'locale': 'el', 'checked': True}],
            'export_what': 'all',
            })

        response = self._do_upload(
            '# <span class="">%s</span>\n' % SKILL_DESC +
            '#: GCB-1|name|string|skill:1:el:0\n'
            '#| msgid ""\n' +
            'msgid "%s"\n' % SKILL_DESC +
            'msgstr "%s"\n' % SKILL_DESC[::-1])
        self.assertIn(
            '<response><status>200</status><message>Success.</message>',
            response.body)

        # Fetch the translation bundle and verify that the description has
        # been changed to the reversed-order string
        bundle = i18n_dashboard.ResourceBundleDAO.load(str(bundle_key))
        self.assertEquals(bundle.dict['description']['data'][0]['target_value'],
                          SKILL_DESC[::-1])


class SkillCompletionTrackerTests(BaseSkillMapTests):
    """Hanldes the access and modification of the skill progress."""

    def _add_student_and_progress(self):
        # progress string for students
        student_progress = {
            self.sa.id: {
                SkillCompletionTracker.COMPLETED: time.time() - 100,
                SkillCompletionTracker.IN_PROGRESS: time.time() - 200
            },
            self.sb.id: {
                SkillCompletionTracker.IN_PROGRESS: time.time()
            },
        }
        self.student = models.Student(user_id='1')
        self.student.put()
        self.progress = models.StudentPropertyEntity.create(
            student=self.student,
            property_name=SkillCompletionTracker.PROPERTY_KEY)
        self.progress.value = transforms.dumps(student_progress)
        self.progress.put()

    def _create_linear_progress(self):
        uid = self.unit.unit_id
        # progress string for students
        student_progress = {
            'u.{}.l.{}'.format(uid, self.lesson1.lesson_id): 2,
            'u.{}.l.{}'.format(uid, self.lesson2.lesson_id): 2
        }

        student = models.Student(user_id='1')
        student.put()
        tracker = self.course.get_progress_tracker()
        comp = tracker.get_or_create_progress(student)
        comp.value = transforms.dumps(student_progress)
        comp.put()

    def test_get_skill_progress(self):
        """Looks in the db for the progress of the skill."""
        self._build_sample_graph()
        self._add_student_and_progress()
        tracker = SkillCompletionTracker()
        result = tracker.get_skills_progress(
            self.student, [self.sa.id, self.sb.id, self.sc.id])
        self.assertEqual(SkillCompletionTracker.COMPLETED,
                         result[self.sa.id][0])
        self.assertEqual(SkillCompletionTracker.IN_PROGRESS,
                         result[self.sb.id][0])
        self.assertEqual(SkillCompletionTracker.NOT_ATTEMPTED,
                         result[self.sc.id][0])

    def test_get_non_existent_skill_progress(self):
        """Asks for the progress of a non existing StudentPropertyEntity."""
        self._build_sample_graph()
        student = models.Student(user_id='1')
        tracker = SkillCompletionTracker()
        result = tracker.get_skills_progress(student, [self.sc.id])
        self.assertEqual(SkillCompletionTracker.NOT_ATTEMPTED,
                         result[self.sc.id][0])

    def test_update_skill_progress(self):
        progress_value = {}
        skill = 1
        start_time = time.time()
        completed = SkillCompletionTracker.COMPLETED
        SkillCompletionTracker.update_skill_progress(progress_value, skill,
                                                  completed)
        end_time = time.time()
        # Repeat, the timestamp should not be affected.
        SkillCompletionTracker.update_skill_progress(progress_value, skill,
                                                  completed)
        skill = str(skill)
        self.assertIn(skill, progress_value)
        self.assertIn(completed, progress_value[skill])
        self.assertLessEqual(start_time, progress_value[skill][completed])
        self.assertLessEqual(progress_value[skill][completed], end_time)

    def test_recalculate_progress(self):
        """Calculates the skill progress from the lessons."""
        self._build_sample_graph()
        self._create_lessons()  # 3 lessons in unit 1
        self.student = models.Student(user_id='1')
        self._create_linear_progress()  # Lesson 1 and 2 completed
        self.lesson1.properties[SKILLS_KEY] = [self.sa.id]
        self.lesson2.properties[SKILLS_KEY] = [self.sb.id]
        self.lesson3.properties[SKILLS_KEY] = [self.sa.id,
                                                          self.sc.id]
        self.course.save()

        tracker = SkillCompletionTracker(self.course)
        lprogress_tracker = UnitLessonCompletionTracker(self.course)
        lprogress = lprogress_tracker.get_or_create_progress(self.student)
        expected = {
            self.sa: tracker.IN_PROGRESS,
            self.sb: tracker.COMPLETED,
            self.sc: tracker.NOT_ATTEMPTED
        }
        for skill, expected_progress in expected.iteritems():
            self.assertEqual(expected_progress,
                tracker.recalculate_progress(lprogress_tracker,
                                             lprogress, skill))

    def test_update_skills_to_completed(self):
        """Calculates the state from the linear progress."""
        self._build_sample_graph()
        self._create_lessons()  # 3 lessons in unit 1
        self._add_student_and_progress()  # sa completed, sb in progress
        self._create_linear_progress()  # Lesson 1 and 2 completed
        self.lesson1.properties[SKILLS_KEY] = [self.sa.id,
                                                          self.sb.id]
        self.course.save()

        start_time = time.time()
        tracker = SkillCompletionTracker(self.course)
        lprogress_tracker = UnitLessonCompletionTracker(self.course)
        lprogress = lprogress_tracker.get_or_create_progress(self.student)
        tracker.update_skills(self.student, lprogress, self.lesson1.lesson_id)
        # Nothing changes with sa
        sprogress = models.StudentPropertyEntity.get(
            self.student, SkillCompletionTracker.PROPERTY_KEY)
        progress_value = transforms.loads(sprogress.value)
        self.assertIn(tracker.COMPLETED, progress_value[str(self.sa.id)])
        self.assertLessEqual(
            progress_value[str(self.sa.id)][tracker.COMPLETED], start_time)

        # Update in sb
        self.assertIn(tracker.COMPLETED, progress_value[str(self.sb.id)])
        self.assertGreaterEqual(
            progress_value[str(self.sb.id)][tracker.COMPLETED], start_time)

    def test_update_recalculate_no_skill_map(self):
        self._build_sample_graph()
        self._create_lessons()  # 3 lessons in unit 1
        self._add_student_and_progress()  # sa completed, sb in progress
        lprogress_tracker = UnitLessonCompletionTracker(self.course)
        lprogress = lprogress_tracker.get_or_create_progress(self.student)
        tracker = SkillCompletionTracker()
        # Just does not raise any error
        tracker.update_skills(self.student, lprogress, self.lesson1.lesson_id)
        tracker.recalculate_progress(lprogress_tracker, lprogress, self.sa)


class CompetencyMeasureTests(BaseSkillMapTests):

    def setUp(self):
        super(CompetencyMeasureTests, self).setUp()
        self.skill_id = 1
        self.skill_2_id = 2
        self.user_id = 321

    def test_success_rate_measure(self):
        measure = competency.SuccessRateCompetencyMeasure.load(
            self.user_id, self.skill_id)

        # Expect 0.0 when nothing has been set
        self.assertEqual(0.0, measure.score)

        # Expect to track percentage correct
        measure.add_score(1.0)
        self.assertEqual(1.0, measure.score)
        measure.add_score(0.0)
        self.assertEqual(0.5, measure.score)

        # Expect save and load
        measure.save()
        measure = competency.SuccessRateCompetencyMeasure.load(
            self.user_id, self.skill_id)
        self.assertEqual(0.5, measure.score)

        self.assertEqual(2, len(measure.scores))

    def test_add_score_to_competency_measure(self):
        updater = competency.CompetencyMeasureRegistry.get_updater(
            self.user_id, self.skill_id)
        updater.add_score(0.0)
        updater.add_score(1.0)
        updater.save()

        measure = competency.SuccessRateCompetencyMeasure.load(
            self.user_id, self.skill_id)
        self.assertEqual(0.5, measure.score)

    def test_safe_key(self):
        def transform_function(pii_str):
            return 'trans(%s)' % pii_str

        measure = competency.SuccessRateCompetencyMeasure.load(
            self.user_id, self.skill_id)
        measure.save()

        entity = competency.CompetencyMeasureEntity.get_by_key_name(
            competency.CompetencyMeasureEntity.create_key_name(
                self.user_id, self.skill_id,
                competency.SuccessRateCompetencyMeasure.__name__))
        safe_key = competency.CompetencyMeasureEntity.safe_key(
            entity.key(), transform_function)
        self.assertEqual(
            safe_key.name(),
            'trans(%s):%s:SuccessRateCompetencyMeasure' % (
                self.user_id, self.skill_id))

    def test_bulk_load_competency_measure(self):
        measures = competency.SuccessRateCompetencyMeasure.bulk_load(
            self.user_id, [self.skill_id, self.skill_2_id])
        self.assertEqual(2, len(measures))
        self.assertEqual(0.0, measures[0].score)
        self.assertEqual(0.0, measures[1].score)


class EventListenerTests(BaseSkillMapTests):

    def setUp(self):
        # Set up three questions. The first will be stand-alone and the other
        # two will be in a group. Tag them with skill A and Skill B as follows:
        #   qu0: a
        #   qu1: a, b
        #   qu2: b

        super(EventListenerTests, self).setUp()
        self.qu0 = self._create_mc_question('Question 0')
        self.qu1 = self._create_mc_question('Question 1')
        self.qu2 = self._create_mc_question('Question 2')
        self.qgp = self._create_question_group('Group', [self.qu1, self.qu2])
        self._build_sample_graph()

        self.qu0.dict[SKILLS_KEY] = [self.sa.id]
        self.qu1.dict[SKILLS_KEY] = [self.sa.id, self.sb.id]
        self.qu2.dict[SKILLS_KEY] = [self.sb.id]
        models.QuestionDAO.save_all([self.qu0, self.qu1, self.qu2])

        self.single_item_data = {
            'instanceid': 'instanceid-0',
            'type': 'QuestionGroup',
            'location': 'http://localhost:8081/events/unit?unit=2&lesson=3',
            'quids': [self.qu1.id, self.qu2.id],
            'containedTypes': ['McQuestion', 'McQuestion'],
            'answer': [[0], [1]],
            'individualScores': [1, 0],
            'score': 0
        }

        actions.login('user@foo.com')
        self.user = users.get_current_user()

    def tearDown(self):
        actions.logout()
        super(EventListenerTests, self).tearDown()

    def _get_single_item_data(self, qu1score, qu2score):
        return {
            'instanceid': 'instanceid-0',
            'type': 'QuestionGroup',
            'location': 'http://localhost:8081/events/unit?unit=2&lesson=3',
            'quids': [self.qu1.id, self.qu2.id],
            'containedTypes': ['McQuestion', 'McQuestion'],
            'answer': [[0], [1]],
            'individualScores': [qu1score, qu2score],
            'score': 0
        }

    def _get_many_item_data(self, qu0score, qu1score, qu2score):
        return {
            'type': 'scored-lesson',
            'location': 'http://localhost:8081/events/unit?unit=2&lesson=3',
            'quids': {
                'instanceid-0': str(self.qu0.id),
                'instanceid-1': [self.qu1.id, self.qu2.id]
            },
            'containedTypes': {
                'instanceid-0': 'McQuestion',
                'instanceid-1': ['McQuestion', 'McQuestion']
            },
            'answers': {
                'version': '1.5',
                'instanceid-0': [0],
                'instanceid-1': [[1], [0]]
            },
            'individualScores': {
                'instanceid-0': qu0score,
                'instanceid-1': [qu1score, qu2score]
            },
            'score': 2
        }

    def _record_and_expect(self, evt_type, data, sa_measure, sb_measure):
        competency.record_event_listener(evt_type, self.user, data)

        measure = competency.SuccessRateCompetencyMeasure.load(
            self.user.user_id(), self.sa.id)
        self.assertEqual(sa_measure, measure.score)
        measure = competency.SuccessRateCompetencyMeasure.load(
            self.user.user_id(), self.sb.id)
        self.assertEqual(sb_measure, measure.score)


    def test_record_tag_assessment(self):
        # Running total: sa[ 1 / 1 ], sb[ 1 / 2 ]
        data = self._get_single_item_data(1, 0)
        self._record_and_expect('tag-assessment', data, 1.0, 0.5)

        # Running total: sa[ 1 / 2 ], sb[ 2 / 4 ]
        data = self._get_single_item_data(0, 1)
        self._record_and_expect('tag-assessment', data, 0.5, 0.5)

        # Running total: sa[ 1 / 3 ], sb[ 2 / 6 ]
        data = self._get_single_item_data(0, 0)
        self._record_and_expect('tag-assessment', data, 1.0 / 3, 1.0 / 3)

    def test_record_attempt_lesson(self):
        # Running total: sa[ 2 / 2 ], sb[ 1 / 2 ]
        data = self._get_many_item_data(1, 1, 0)
        self._record_and_expect('attempt-lesson', data, 1.0, 0.5)

        # Running total: sa[ 3 / 4 ], sb[ 3 / 4 ]
        data = self._get_many_item_data(0, 1, 1)
        self._record_and_expect('attempt-lesson', data, 0.75, 0.75)

        # Running total: sa[ 3 / 6 ], sb[ 3 / 6 ]
        data = self._get_many_item_data(0, 0, 0)
        self._record_and_expect('attempt-lesson', data, 0.5, 0.5)

    def test_record_submit_assessment(self):
        # Running total: sa[ 2 / 2 ], sb[ 1 / 2 ]
        data = {'values': self._get_many_item_data(1, 1, 0)}
        self._record_and_expect('submit-assessment', data, 1.0, 0.5)

        # Running total: sa[ 3 / 4 ], sb[ 3 / 4 ]
        data = {'values': self._get_many_item_data(0, 1, 1)}
        self._record_and_expect('submit-assessment', data, 0.75, 0.75)

        # Running total: sa[ 3 / 6 ], sb[ 3 / 6 ]
        data = {'values': self._get_many_item_data(0, 0, 0)}
        self._record_and_expect('submit-assessment', data, 0.5, 0.5)

    def test_do_nothing_with_unrecognized_event_type(self):
        competency.record_event_listener('some-other-event-type', self.user, {})
        measure = competency.SuccessRateCompetencyMeasure.load(
            self.user.user_id(), self.sa.id)
        self.assertEqual(0.0, measure.score)
        measure = competency.SuccessRateCompetencyMeasure.load(
            self.user.user_id(), self.sb.id)
        self.assertEqual(0.0, measure.score)


class LessonHeaderTests(BaseSkillMapTests):

    def _create_lessons_with_skills(self):
        # Create skills
        self.skill_graph = SkillGraph.load()
        self.sa = self.skill_graph.add(Skill.build('a', ''))
        self.sb = self.skill_graph.add(Skill.build('b', ''))
        self.skill_graph.add_prerequisite(self.sa.id, self.sb.id)

        # Create lessons
        self.unit = self.course.add_unit()
        self.unit.title = 'Test Unit'
        self.lesson1 = self.course.add_lesson(self.unit)
        self.lesson1.title = 'Test Lesson 1'
        self.lesson2 = self.course.add_lesson(self.unit)
        self.lesson2.title = 'Test Lesson 2'

        # Assign skills to lessons
        # lesson 1 has one skill
        self.lesson1.properties[SKILLS_KEY] = [self.sa.id]
        # lesson 2 has both skills
        self.lesson2.properties[SKILLS_KEY] = [
                self.sa.id, self.sb.id]

    def test_lesson_header_callbacks(self):
        """Happy path test for lesson header callback."""

        # Create lessons and skills for course. The header only appears if our
        # lessons actually have skills associated with them.
        self._create_lessons_with_skills()
        self.course.save()
        actions.login(ADMIN_EMAIL)

        # Create and add new callback to lesson header
        title = 'Hello title'
        content = 'Hello world!'
        def dummy_callback(handler, app_context, unit, lesson, student):
            return {'title': title, 'content': content}

        HEADER_CALLBACKS['dummy'] = dummy_callback

        # Request a unit page in the sample course
        unit_url = self.base + '/unit?unit=1&lesson=2'
        response = self.get(unit_url)

        # Check that the response contains the given title and content
        body = response.body
        self.assertIn(title, body)
        self.assertIn(content, body)
