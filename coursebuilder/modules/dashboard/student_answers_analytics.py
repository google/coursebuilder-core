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

import ast
from mapreduce import context

from common import schema_fields
from common import tags
from models import courses
from models import data_sources
from models import jobs
from models import models
from models import transforms
from tools import verify

MAX_INCORRECT_REPORT = 5


class StudentAnswersStatsGenerator(jobs.MapReduceJob):

    @staticmethod
    def get_description():
        return 'student answers'

    @staticmethod
    def entity_class():
        return models.StudentAnswersEntity

    def build_additional_mapper_params(self, app_context):
        """Build map: question-usage-ID to {question ID, unit ID, sequence}.

        When a question or question-group is mentioned on a CourseBuilder
        HTML page, it is identified by a unique opaque ID which indicates
        *that usage* of a particular question.

        Args:
          app_context: Normal context object giving namespace, etc.
        Returns:
          A map of precalculated facts to be made available to mapper
          workerbee instances.
        """

        questions_by_usage_id = {}
        # To know a question's sequence number within an assessment, we need
        # to know how many questions a question group contains.
        question_group_lengths = {}
        for group in models.QuestionGroupDAO.get_all():
            question_group_lengths[str(group.id)] = (
                len(group.question_ids))

        # Run through course.  For each assessment, parse the HTML content
        # looking for questions and question groups.  For each of those,
        # record the unit ID, use-of-item-on-page-instance-ID (a string
        # like 'RK3q5H2dS7So'), and the sequence on the page.  Questions
        # count as one position.  Question groups increase the sequence
        # count by the number of questions they contain.
        course = courses.Course(None, app_context)
        for unit in course.get_units_of_type(verify.UNIT_TYPE_ASSESSMENT):
            sequence_counter = 0
            for component in tags.get_components_from_html(unit.html_content):
                if component['cpt_name'] == 'question':
                    questions_by_usage_id[component['instanceid']] = {
                        'unit': unit.unit_id,
                        'sequence': sequence_counter,
                        'id': component['quid'],
                        }
                    sequence_counter += 1
                elif component['cpt_name'] == 'question-group':
                    questions_by_usage_id[component['instanceid']] = {
                        'unit': unit.unit_id,
                        'sequence': sequence_counter,
                        'id': component['qgid'],
                        }
                    sequence_counter += (
                        question_group_lengths[component['qgid']])
        return {'questions_by_usage_id': questions_by_usage_id}

    @staticmethod
    def build_key(unit, sequence, question_id, question_type):
        return '%s_%d_%s_%s' % (unit, sequence, question_id, question_type)

    @staticmethod
    def parse_key(key):
        unit, sequence, question_id, question_type = key.split('_')
        return unit, int(sequence), question_id, question_type

    @staticmethod
    def map_handle_cb_1_5(questions_info, unit_id, unit_responses):
        ret = []
        contained_types = unit_responses['containedTypes']

        for usage_id, answers in unit_responses['answers'].items():
            if usage_id not in questions_info:
                continue  # Skip items from no-longer-present questions.

            # Note: The variable names here are in plural, but for single
            # questions, 'types', 'scores' and 'answers' contain just one
            # item.  (whereas for question groups, these are all arrays)
            info = questions_info[usage_id]
            types = contained_types[usage_id]
            scores = unit_responses['individualScores'][usage_id]

            # Single question - give its answer.
            if types == 'McQuestion' or types == 'SaQuestion':
                ret.append(
                    (StudentAnswersStatsGenerator.build_key(
                        unit_id, info['sequence'], info['id'], types),
                     (answers, scores)))

            # Question group. Fetch IDs of sub-questions, which are packed as
            # <group-usage-id>.<sequence>.<question-id>.
            # Order by <sequence>, which is 0-based within question-group.
            elif isinstance(types, list):

                # Sort IDs by sequence-within-group number.  Need these in
                # order so that we can simply zip() IDs together with other
                # items.
                packed_ids = unit_responses[usage_id].keys()
                packed_ids.sort(key=lambda packed: int(packed.split('.')[1]))

                for packed_id, answer, q_type, score in zip(
                    packed_ids, answers, types, scores):

                    _, seq, q_id = packed_id.split('.')
                    ret.append(
                        (StudentAnswersStatsGenerator.build_key(
                            unit_id, info['sequence'] + int(seq), q_id, q_type),
                         (answer, score)))

            # TODO(mgainer): Emit warning counter here if we don't grok
            # the 'types' value.
        return ret

    @staticmethod
    def map(student_answers):
        params = context.get().mapreduce_spec.mapper.params
        questions_by_usage_id = params['questions_by_usage_id']
        all_answers = transforms.loads(student_answers.data)
        for unit_id, unit_responses in all_answers.items():

            # Is this a CourseBuilder Question/QuestionGroup set of answers?
            if ('containedTypes' in unit_responses and
                unit_responses['version'] == '1.5'):
                for answer in StudentAnswersStatsGenerator.map_handle_cb_1_5(
                    questions_by_usage_id, unit_id, unit_responses):
                    yield answer
            # TODO(mgainer): Emit warning counter here if we don't grok
            # the response type.  We will need to cope with Oppia and
            # XBlocks responses.  Do that in a follow-on CL.

    @staticmethod
    def reduce(key, answers_and_scores_list):
        correct_answers = {}
        incorrect_answers = {}
        unit_id, sequence, question_id, question_type = (
            StudentAnswersStatsGenerator.parse_key(key))
        unit_id = int(unit_id)
        question_id = long(question_id)

        for packed_data in answers_and_scores_list:
            answers, score = ast.literal_eval(packed_data)
            if question_type == 'SaQuestion':
                if score > 0:
                    # Note: 'answers' only contains one item (not a list) for
                    # SaQuestion.
                    correct_answers.setdefault(answers, 0)
                    correct_answers[answers] += 1
                else:
                    incorrect_answers.setdefault(answers, 0)
                    incorrect_answers[answers] += 1
            elif question_type == 'McQuestion':
                # For multiple-choice questions, we only get one overall score
                # for the question as a whole.  This means that some choices
                # may be incorrect.  Happily, though, the only reason we care
                # about the distinction between correct/incorrect is to limit
                # the quantity of output for incorrect answers.  Since
                # multiple-choice questions are inherently limited, just
                # call all of the answers 'correct'.
                for sub_answer in answers:
                    correct_answers.setdefault(sub_answer, 0)
                    correct_answers[sub_answer] += 1

        def build_reduce_dict(unit_id, sequence, question_id, is_valid,
                              answer, count):
            # NOTE: maintain members in parallel with get_schema() below.
            return ({'unit_id': unit_id,
                     'sequence': sequence,
                     'question_id': question_id,
                     'is_valid': is_valid,
                     'answer': answer,
                     'count': count})

        # Emit tuples for each of the correct answers.
        for answer, count in correct_answers.items():
            yield(build_reduce_dict(unit_id, sequence, question_id, True,
                                    answer, count))

        # Emit tuples for incorrect answers.  Free-form answer fields can have
        # a lot of wrong answers.  Only report the most-commonly-occuring N
        # answers, and report a total for the rest.
        if incorrect_answers:
            sorted_incorrect = [(v, k) for k, v in incorrect_answers.items()]
            sorted_incorrect.sort()
            sorted_incorrect.reverse()
            for count, answer in sorted_incorrect[0:MAX_INCORRECT_REPORT]:
                yield(build_reduce_dict(unit_id, sequence, question_id, False,
                                        answer, count))
            for count, _ in sorted_incorrect[MAX_INCORRECT_REPORT:]:
                yield(build_reduce_dict(unit_id, sequence, question_id, False,
                                        'Other Incorrect Answers', count))


class QuestionAnswersDataSource(data_sources.AbstractSmallRestDataSource):

    @staticmethod
    def required_generators():
        return [StudentAnswersStatsGenerator]

    @classmethod
    def get_name(cls):
        return 'question_answers'

    @classmethod
    def get_title(cls):
        return 'Question Answers'

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log):
        # NOTE: maintain members in parallel with build_reduce_dict() above.
        reg = schema_fields.FieldRegistry(
            'Question Answers',
            description='Summarized results for each use of each question')
        reg.add_property(schema_fields.SchemaField(
            'unit_id', 'Unit ID', 'string',
            description='ID of unit in which question appears.  Key to Unit'))
        reg.add_property(schema_fields.SchemaField(
            'sequence', 'Sequence', 'integer',
            description='Ordering within course for question.'))
        reg.add_property(schema_fields.SchemaField(
            'question_id', 'Question ID', 'string',
            description='ID of question.  Key to models.QuestionDAO'))
        reg.add_property(schema_fields.SchemaField(
            'is_valid', 'Is Valid', 'boolean',
            description='Whether the answer is "valid".  An answer is '
            'valid if it is one of the defined answers to the question.  '
            'All answers to multiple-choice questions, correct or incorrect '
            'are considered valid.  Answers to single-answer questions '
            '(i.e., type-in-an-answer) questions are only considered valid '
            'if they earned a positive score.  The most-commonly guessed '
            'wrong answers are also reported with this field set to False. '
            'The count of the rest of the wrong answers is lumped into a '
            'single item, "Other Incorrect Answers".'))
        reg.add_property(schema_fields.SchemaField(
            'answer', 'Answer', 'string',
            description='The actually-selected answer'))
        reg.add_property(schema_fields.SchemaField(
            'count', 'Count', 'integer',
            description='The number of times this answer was given.'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, unused_source_context, unused_schema,
                     unused_catch_and_log, unused_page_number,
                     student_answers_job):

        def ordering(a1, a2):
            return (cmp(a1['unit_id'], a2['unit_id']) or
                    cmp(a1['sequence'], a2['sequence']) or
                    cmp(a2['is_valid'], a1['is_valid']) or
                    cmp(a1['answer'], a2['answer']))
        ret = list(jobs.MapReduceJob.get_results(student_answers_job))
        ret.sort(ordering)
        return ret, 0


class CourseQuestionsDataSource(data_sources.AbstractSmallRestDataSource):

    @classmethod
    def get_name(cls):
        return 'course_questions'

    @classmethod
    def get_title(cls):
        return 'Course Questions'

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log):
        # NOTE: maintain members in parallel with build_reduce_dict() above.
        reg = schema_fields.FieldRegistry(
            'Course Questions',
            description='Facts about each usage of each question in a course.')
        reg.add_property(schema_fields.SchemaField(
            'question_id', 'Question ID', 'string',
            description='ID of question.  Key to models.QuestionDAO'))
        reg.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string',
            description='User-entered description of question.'))

        # pylint: disable-msg=unused-variable
        arrayMember = schema_fields.SchemaField(
            'option_text', 'Option Text', 'string',
            description='Text of the multiple-choice option')
        reg.add_property(schema_fields.FieldArray(
            'choices', 'Choices', item_type=arrayMember,
            description='Multiple-choice question options'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, unused_source_context, unused_schema,
                     unused_catch_and_log, unused_page_number):

        # Look up questions from DB.
        questions = []
        for question in models.QuestionDAO.get_all():
            item = {
                'question_id': question.id,
                'description': question.dict['description'],
                'text': question.dict['question'],
                }
            if 'choices' in question.dict:
                item['choices'] = [c['text'] for c in question.dict['choices']]
            else:
                item['choices'] = []
            questions.append(item)
        return questions, 0


class CourseUnitsDataSource(data_sources.AbstractSmallRestDataSource):

    @classmethod
    def get_name(cls):
        return 'course_units'

    @classmethod
    def get_title(cls):
        return 'Course Units'

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log):
        # NOTE: maintain members in parallel with build_reduce_dict() above.
        reg = schema_fields.FieldRegistry(
            'Units',
            description='Units (units, assessments, links) in a course')
        reg.add_property(schema_fields.SchemaField(
            'type', 'Type', 'string',
            description='Type of unit. "U":unit, "A":assessment, "L":link'))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            description='Display title of the unit'))
        reg.add_property(schema_fields.SchemaField(
            'release_date', 'Release Date', 'string',
            description='Date the unit is to be made publicly available'))
        reg.add_property(schema_fields.SchemaField(
            'properties', 'Properties', 'string',
            description='Site-specific additional properties added to unit'))
        reg.add_property(schema_fields.SchemaField(
            'weight', 'Weight', 'integer',
            description='Weight to give to the unit when scoring.'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, unused_source_context, unused_schema,
                     unused_catch_and_log, unused_page_number):

        # Look up questions from DB.
        units = []
        for unit in courses.Course(None, app_context).get_units():
            units.append({
                'unit_id': unit.unit_id,
                'type': unit.type,
                'title': unit.title,
                'release_date': unit.release_date,
                'now_available': unit.now_available,
                'properties': unit.properties,
                'weight': unit.weight
                })
        return units, 0
