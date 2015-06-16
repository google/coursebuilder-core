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

"""Module to provide skill recommendations and non-linear course navigation."""

__author__ = 'Boris Roussev (borislavr@google.com)'


class BaseSkillRecommender(object):
    """Base class to model the behavior of a skill recommendation algorithm."""

    def __init__(self, skill_map):
        self._skill_map = skill_map

    def recommend(self):
        """Recommend a user a prioritized list of skills to learn."""
        raise NotImplementedError()


class TopoSkillRecommender(BaseSkillRecommender):
    """Recommend skills with satisfied prerequisites in toposort."""

    def recommend(self):
        # skills with high and medium proficiency scores
        learned = []
        # skills with learned or empty set of predecessors
        recommended = []

        for skill in self._skill_map.skills(sort_by='prerequisites'):
            if skill.proficient:
                learned.append(skill)
            elif all(x.proficient for x in skill.prerequisites):
                recommended.append(skill)

        return recommended, learned


class SkillRecommender(object):
    """Static factory for skill recommenders."""

    @staticmethod
    def instance(skill_map, type_name=None):
        type_name = type_name or 'TopoSkillRecommender'
        if type_name == 'TopoSkillRecommender':
            return TopoSkillRecommender(skill_map)
        raise AssertionError('Unexpected recommender: %s.' % type_name)

