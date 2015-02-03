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

from common import crypto
from controllers import sites
from models import courses
from models import transforms
from modules.skill_map.skill_map import LESSON_SKILL_LIST_KEY
from modules.skill_map.skill_map import Skill
from modules.skill_map.skill_map import SkillGraph
from modules.skill_map.skill_map import SkillMap
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
        context = actions.simple_add_course(
            COURSE_NAME, ADMIN_EMAIL, 'Skills Map Course')
        self.old_namespace = namespace_manager.get_namespace()
        namespace_manager.set_namespace('ns_%s' % COURSE_NAME)

        self.course = courses.Course(None, context)

    def tearDown(self):
        del sites.Registry.test_overrides[sites.GCB_COURSES_CONFIG.name]
        namespace_manager.set_namespace(self.old_namespace)
        super(BaseSkillMapTests, self).tearDown()


class SkillGraphTests(BaseSkillMapTests):

    def test_add_skill(self):
        # Skill map is initially empty
        skill_graph = SkillGraph.load()
        self.assertEqual(0, len(skill_graph.skills))

        # Add a single skill
        skill = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_id = skill_graph.add(skill)
        self.assertEqual(1, len(skill_graph.skills))

        # Retrieve the skill by id
        skill_by_id = skill_graph.get(skill_id)
        self.assertEqual(SKILL_NAME, skill_by_id.name)
        self.assertEqual(SKILL_DESC, skill_by_id.description)

    def test_add_skill_twice_is_rejected(self):
        skill_graph = SkillGraph.load()

        # Add a single skill
        skill = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_id = skill_graph.add(skill)
        self.assertEqual(1, len(skill_graph.skills))

        # Retrieve the skill by id and add it again
        skill_by_id = skill_graph.get(skill_id)
        with self.assertRaises(AssertionError):
            skill_id = skill_graph.add(skill_by_id)

    def test_delete_skill(self):
        # Skill map is initially empty
        skill_graph = SkillGraph.load()
        self.assertEqual(0, len(skill_graph.skills))

        # Add a single skill
        skill = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_id = skill_graph.add(skill)
        self.assertEqual(1, len(skill_graph.skills))

        # Delete the skill and expect empty
        skill_graph.delete(skill_id)
        self.assertEqual(0, len(skill_graph.skills))

    def test_delete_skill_with_successors(self):
        skill_graph = SkillGraph.load()

        skill_1 = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_1_id = skill_graph.add(skill_1)
        skill_2 = Skill.build(SKILL_NAME_2, SKILL_DESC_2)
        skill_2_id = skill_graph.add(skill_2)

        # Skill 1 is a prerequisite for Skill 2
        skill_graph.add_prerequisite(skill_2_id, skill_1_id)

        skill_graph.delete(skill_1_id)
        self.assertEqual(1, len(skill_graph.skills))
        self.assertEqual(skill_2_id, skill_graph.skills[0].id)
        self.assertEqual(0, len(skill_graph.prerequisites(skill_2_id)))

    def test_add_prerequisite(self):
        skill_graph = SkillGraph.load()

        skill_1 = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_1_id = skill_graph.add(skill_1)
        skill_2 = Skill.build(SKILL_NAME_2, SKILL_DESC_2)
        skill_2_id = skill_graph.add(skill_2)

        # Skill 1 is a prerequisite for Skill 2
        skill_graph.add_prerequisite(skill_2_id, skill_1_id)

        skill_graph = SkillGraph.load()
        self.assertEqual(1, len(skill_graph.prerequisites(skill_2_id)))
        self.assertEqual(
            skill_1_id, skill_graph.prerequisites(skill_2_id)[0].id)

        self.assertEqual(1, len(skill_graph.successors(skill_1_id)))
        self.assertEqual(skill_2_id, skill_graph.successors(skill_1_id)[0].id)

    def test_add_missing_prerequisites_rejected(self):
        skill_graph = SkillGraph.load()

        with self.assertRaises(AssertionError):
            skill_graph.add_prerequisite('missing', 'also missing')

        skill_1 = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_1_id = skill_graph.add(skill_1)

        with self.assertRaises(AssertionError):
            skill_graph.add_prerequisite('missing', skill_1_id)

        with self.assertRaises(AssertionError):
            skill_graph.add_prerequisite(skill_1_id, 'also missing')

    def test_add_loop_rejected(self):
        """Test that cannot add a skill with a length-1 cycle."""
        skill_graph = SkillGraph.load()

        skill_1 = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_1_id = skill_graph.add(skill_1)

        with self.assertRaises(AssertionError):
            skill_graph.add_prerequisite(skill_1_id, skill_1_id)

    def test_add_duplicate_prerequisites_rejected(self):
        skill_graph = SkillGraph.load()

        skill_1 = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_1_id = skill_graph.add(skill_1)
        skill_2 = Skill.build(SKILL_NAME_2, SKILL_DESC_2)
        skill_2_id = skill_graph.add(skill_2)

        skill_graph.add_prerequisite(skill_2_id, skill_1_id)
        with self.assertRaises(AssertionError):
            skill_graph.add_prerequisite(skill_2_id, skill_1_id)

    def test_delete_prerequisite(self):
        skill_graph = SkillGraph.load()

        skill_1 = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_1_id = skill_graph.add(skill_1)
        skill_2 = Skill.build(SKILL_NAME_2, SKILL_DESC_2)
        skill_2_id = skill_graph.add(skill_2)
        skill_3 = Skill.build(SKILL_NAME_3, SKILL_DESC_3)
        skill_3_id = skill_graph.add(skill_3)

        # Skills 1 and 2 are prerequisites for Skill 3
        skill_graph.add_prerequisite(skill_3_id, skill_1_id)
        skill_graph.add_prerequisite(skill_3_id, skill_2_id)

        skill_graph = SkillGraph.load()
        self.assertEqual(2, len(skill_graph.prerequisites(skill_3_id)))

        # Delete skill 1 as a prerequisite and expect that only skill 2 is a
        # prerequisite now
        skill_graph.delete_prerequisite(skill_3_id, skill_1_id)

        self.assertEqual(1, len(skill_graph.prerequisites(skill_3_id)))
        self.assertEqual(
            skill_2_id, skill_graph.prerequisites(skill_3_id)[0].id)

    def test_delete_missing_prerequisites_rejected(self):
        skill_graph = SkillGraph.load()

        with self.assertRaises(AssertionError):
            skill_graph.delete_prerequisite('missing', 'also missing')

        skill_1 = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_1_id = skill_graph.add(skill_1)
        skill_2 = Skill.build(SKILL_NAME_2, SKILL_DESC_2)
        skill_2_id = skill_graph.add(skill_2)

        with self.assertRaises(AssertionError):
            skill_graph.delete_prerequisite('missing', skill_1_id)

        with self.assertRaises(AssertionError):
            skill_graph.delete_prerequisite(skill_1_id, 'also missing')

        # Also reject deletion of a prerequisite if the skill exists but is not
        # currently a prerequisite
        with self.assertRaises(AssertionError):
            skill_graph.delete_prerequisite(skill_1_id, skill_2_id)

    def test_multiple_successors(self):
        skill_graph = SkillGraph.load()

        skill_1 = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_1_id = skill_graph.add(skill_1)
        skill_2 = Skill.build(SKILL_NAME_2, SKILL_DESC_2)
        skill_2_id = skill_graph.add(skill_2)
        skill_3 = Skill.build(SKILL_NAME_3, SKILL_DESC_3)
        skill_3_id = skill_graph.add(skill_3)

        # Skills 2 and 3 are successors of Skill 1
        skill_graph.add_prerequisite(skill_2_id, skill_1_id)
        skill_graph.add_prerequisite(skill_3_id, skill_1_id)

        skill_graph = SkillGraph.load()
        successor_ids = {s.id for s in skill_graph.successors(skill_1_id)}
        self.assertEqual({skill_2_id, skill_3_id}, successor_ids)


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

    def tearDown(self):
        self.course.clear_current()
        super(SkillMapTests, self).tearDown()

    def test_get_lessons_for_skill(self):
        skill_graph = SkillGraph.load()
        skill_1 = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_1_id = skill_graph.add(skill_1)
        skill_2 = Skill.build(SKILL_NAME_2, SKILL_DESC_2)
        skill_2_id = skill_graph.add(skill_2)

        # lesson 1 has one skill
        self.lesson1.properties[LESSON_SKILL_LIST_KEY] = [skill_1_id]
        # lesson 2 has no skills
        # lesson 3 has both skills
        self.lesson3.properties[LESSON_SKILL_LIST_KEY] = [
                skill_1_id, skill_2_id]
        self.course.save()

        skill_map = SkillMap.load(self.course.app_context)

        lessons = skill_map.get_lessons_for_skill(skill_1_id)
        self.assertEqual(2, len(lessons))
        self.assertEqual(self.lesson1.lesson_id, lessons[0].lesson_id)
        self.assertEqual(self.lesson3.lesson_id, lessons[1].lesson_id)

        lessons = skill_map.get_lessons_for_skill(skill_2_id)
        self.assertEqual(1, len(lessons))
        self.assertEqual(self.lesson3.lesson_id, lessons[0].lesson_id)

    def test_get_lessons_returns_empty_list_when_no_skills_assigned(self):
        skill_graph = SkillGraph.load()
        skill = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_id = skill_graph.add(skill)

        skill_map = SkillMap.load(self.course.app_context)

        lessons = skill_map.get_lessons_for_skill(skill_id)
        self.assertIsNotNone(lessons)
        self.assertEqual(0, len(lessons))


class SkillListRestHandlerTests(BaseSkillMapTests):
    URL = 'rest/modules/skill_map/skill_list'

    def test_rejected_if_not_authorized(self):
        # Not logged in
        response = transforms.loads(self.get(self.URL).body)
        self.assertEqual(401, response['status'])

        # logged in but not admin
        actions.login('user.foo.com')
        response = transforms.loads(self.get(self.URL).body)
        self.assertEqual(401, response['status'])

        # logged in as admin
        actions.logout()
        actions.login(ADMIN_EMAIL)
        response = transforms.loads(self.get(self.URL).body)
        self.assertEqual(200, response['status'])

    def test_get_skill_list(self):
        skill_graph = SkillGraph.load()

        skill_1 = Skill.build(SKILL_NAME, SKILL_DESC)
        skill_1_id = skill_graph.add(skill_1)
        skill_2 = Skill.build(SKILL_NAME_2, SKILL_DESC_2)
        skill_2_id = skill_graph.add(skill_2)
        skill_3 = Skill.build(SKILL_NAME_3, SKILL_DESC_3)
        skill_3_id = skill_graph.add(skill_3)

        actions.login(ADMIN_EMAIL)
        response = transforms.loads(self.get(self.URL).body)

        self.assertEqual(200, response['status'])
        self.assertIn('xsrf_token', response)

        skill_list = transforms.loads(response['payload'])['skill_list']
        self.assertEqual(3, len(skill_list))

        expected_skill_list = [
            {
                'id': skill_1_id,
                'name': SKILL_NAME,
                'description': SKILL_DESC},
            {
                'id': skill_2_id,
                'name': SKILL_NAME_2,
                'description': SKILL_DESC_2},
            {
                'id': skill_3_id,
                'name': SKILL_NAME_3,
                'description': SKILL_DESC_3}]
        self.assertEqual(expected_skill_list, skill_list)


class SkillRestHandlerTests(BaseSkillMapTests):
    URL = 'rest/modules/skill_map/skill'
    XSRF_TOKEN = 'skill-handler'

    def _put(self, version=None, name=None, description=None, xsrf_token=None):
        request_dict = {
            'xsrf_token': xsrf_token,
            'payload': transforms.dumps({
                'version': version,
                'name': name,
                'description': description})
        }
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

    def test_insert_skill(self):
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
