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

"""Module to model skill map as RDF."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

from cgi import escape
import os

from rdflib import BNode
from rdflib import Graph
from rdflib import Literal
from rdflib import Namespace
from rdflib import RDF
from rdflib import RDFS


class RdfBuilder(object):
    """Builds RDF schema and data representations of skill maps."""

    SCHEMA_URL = '/modules/skill_map/rdf/v1/schema'
    DATA_URL = '/modules/skill_map/rdf/v1/data'

    def __init__(self):
        self.ns_url = self._make_ns_url()
        self.NS = Namespace(self.ns_url)
        self.skill_node_by_id = {}
        self.question_node_by_id = {}
        self.lesson_node_by_id = {}

    @classmethod
    def _make_ns_url(cls):
        if os.environ.get('HTTPS') == 'on':
            scheme = 'https'
        else:
            scheme = 'http'
        return '%s://%s%s#' % (
            scheme, os.environ['HTTP_HOST'], cls.SCHEMA_URL)

    def _add_skills(self, model, skills):
        for skill in skills:
            element = BNode()
            assert skill.id not in self.skill_node_by_id
            self.skill_node_by_id[skill.id] = (skill, element)
            model.add((element, RDF.type, self.NS.skill))
            model.add((element, self.NS.id, Literal(skill.id)))
            model.add((element, RDFS.label, Literal(skill.name)))
            model.add((element, RDFS.comment, Literal(skill.description)))
        for skill in skills:
            for _prev in skill.prerequisites:
                model.add((
                    self.skill_node_by_id[skill.id][1],
                    self.NS.prerequisite,
                    self.skill_node_by_id[_prev.id][1]))

    def _add_questions(self, model, skills):
        for skill in skills:
            for question in skill.questions:
                element = self.question_node_by_id.get(question.id)
                if not element:
                    element = BNode()
                    self.question_node_by_id[question.id] = (question, element)
                    model.add((element, RDF.type, self.NS.question))
                    model.add((element, self.NS.id, Literal(question.id)))
                    model.add((
                        element,
                        RDFS.label,
                        Literal(question.description)))
                model.add((
                    self.skill_node_by_id[skill.id][1],
                    self.NS.assessed_by,
                    self.question_node_by_id[question.id][1]))

    def _add_lessons(self, model, skills):
        for skill in skills:
            for lesson in skill.lessons:
                element = self.lesson_node_by_id.get(lesson.id)
                if not element:
                    element = BNode()
                    self.lesson_node_by_id[lesson.id] = (lesson, element)
                    model.add((element, RDF.type, self.NS.lesson))
                    model.add((element, self.NS.id, Literal(lesson.id)))
                    model.add((element, RDFS.label, Literal(lesson.label)))
                model.add((
                    self.skill_node_by_id[skill.id][1],
                    self.NS.taught_in,
                    self.lesson_node_by_id[lesson.id][1]))

    def _add_entity(self, name, label, comment):
        return """
  <rdf:Description rdf:about="{0}{1}">
    <rdfs:isDefinedBy rdf:resource="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>
    <rdfs:label>{2}</rdfs:label>
    <rdfs:comment>{3}</rdfs:comment>
    <rdf:type rdf:resource="http://www.w3.org/2000/01/rdf-schema#Class"/>
    <rdfs:subClassOf rdf:resource="http://www.w3.org/2000/01/rdf-schema#Class"/>
  </rdf:Description>""".format(
            escape(self.ns_url), escape(name), escape(label), escape(comment))

    def _add_property(self, name, label, comment):
        return """
  <rdf:Description rdf:about="{0}{1}">
    <rdfs:isDefinedBy rdf:resource="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>
    <rdfs:label>{2}</rdfs:label>
    <rdfs:comment>{3}</rdfs:comment>
    <rdf:type rdf:resource="http://www.w3.org/2000/01/rdf-schema#Property"/>
    <rdfs:domain rdf:resource="http://www.w3.org/2000/01/rdf-schema#Class"/>
    <rdfs:range rdf:resource="http://www.w3.org/2000/01/rdf-schema#Literal"/>
  </rdf:Description>""".format(
            escape(self.ns_url), escape(name), escape(label), escape(comment))

    def _add_relation(self, name, label, comment, from_name, to_name):
        return """
  <rdf:Description rdf:about="{0}{1}">
    <rdfs:isDefinedBy rdf:resource="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>
    <rdfs:label>{2}</rdfs:label>
    <rdfs:comment>{3}</rdfs:comment>
    <rdf:type rdf:resource="http://www.w3.org/2000/01/rdf-schema#Property"/>
    <rdfs:domain rdf:resource="{0}{4}"/>
    <rdfs:range rdf:resource="{0}{5}"/>
  </rdf:Description>""".format(
            escape(self.ns_url), escape(name), escape(label), escape(comment),
            escape(from_name), escape(to_name))

    def schema_toxml(self):
        lines = []
        lines.append(self._add_property(
            'Id', 'The Id',
            'An identifier for the object in the system of origin.'))

        lines.append(self._add_entity(
            'Skill', 'The Skill',
            'We use the term "skill" to define knowledge about procedures, '
            'processes, facts, and concepts that can be tested. It is a piece '
            'of knowledge that can be measured or assessed. A skill can have '
            'one or more prerequisite skills.'))
        lines.append(self._add_entity(
            'Lesson', 'The Lesson',
            'The educational material that teaches the skill.'))
        lines.append(self._add_entity(
            'Question', 'The Question',
            'The test verifying that skill has been learned.'))

        lines.append(self._add_relation(
            'Prerequisite', 'The Prerequisite',
            'The skills that are prerequisites for this skill. Prerequisites '
            'are other skills that should be learned before attempting to '
            'learn the current skill.', 'Skill', 'Skill'))
        lines.append(self._add_relation(
            'Assessed_by', 'The Assessed By',
            'The question where current skill is assessed.',
            'Skill', 'Question'))
        lines.append(self._add_relation(
            'Taught_in', 'The Taught In',
            'The lesson where current skill is taught.', 'Skill', 'Lesson'))

        return (
"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
   xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
   xmlns:owl="http://www.w3.org/2002/07/owl#"
>
  <rdf:Description rdf:about="{0}">
    <rdf:type rdf:resource="http://www.w3.org/2002/07/owl#Ontology"/>
    <dc:description>This is the RDF Schema for the Course Builder Skill
      Map.</dc:description>
    <dc:title>
      The Course Builder Skill Map Concepts Vocabulary (GCBSM)</dc:title>
  </rdf:Description>
  {1}
</rdf:RDF>
""".format(escape(self.ns_url), ''.join(lines)))

    def skills_toxml(self, skills):
        model = Graph()
        model.bind("gcbsm", self.NS)  # gcbsm == gcb skill map

        self._add_skills(model, skills)
        self._add_questions(model, skills)
        self._add_lessons(model, skills)

        return model.serialize(format='xml')
