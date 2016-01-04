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
from models import courses
from models import data_sources
from models import event_transforms
from models import jobs
from models import models
from models import transforms


MAX_INCORRECT_REPORT = 5


class StudentAnswersStatsGenerator(jobs.MapReduceJob):

    @staticmethod
    def get_description():
        return 'student answers'

    @staticmethod
    def entity_class():
        return models.StudentAnswersEntity

    def build_additional_mapper_params(self, app_context):
        return {
            'questions_by_usage_id': (
                event_transforms.get_questions_by_usage_id(app_context)),
            'valid_question_ids': (
                event_transforms.get_valid_question_ids()),
            'group_to_questions': (
                event_transforms.get_group_to_questions()),
            'assessment_weights':
                event_transforms.get_assessment_weights(app_context),
            'unscored_lesson_ids':
                event_transforms.get_unscored_lesson_ids(app_context),
            }

    @staticmethod
    def build_key(unit, sequence, question_id, question_type):
        return '%s_%d_%s_%s' % (unit, sequence, question_id, question_type)

    @staticmethod
    def parse_key(key):
        unit, sequence, question_id, question_type = key.split('_')
        return unit, int(sequence), question_id, question_type

    @staticmethod
    def map(student_answers):
        params = context.get().mapreduce_spec.mapper.params
        questions_by_usage_id = params['questions_by_usage_id']
        valid_question_ids = params['valid_question_ids']
        group_to_questions = params['group_to_questions']
        assessment_weights = params['assessment_weights']
        all_answers = transforms.loads(student_answers.data)
        for unit_id, unit_responses in all_answers.items():

            # Is this a CourseBuilder Question/QuestionGroup set of answers?
            if ('containedTypes' in unit_responses and
                unit_responses['version'] == '1.5'):
                for answer in event_transforms.unpack_student_answer_1_5(
                    questions_by_usage_id, valid_question_ids,
                    assessment_weights, group_to_questions, unit_responses,
                    timestamp=0):
                    yield (StudentAnswersStatsGenerator.build_key(
                        unit_id, answer.sequence, answer.question_id,
                        answer.question_type), (answer.answers, answer.score))
            # TODO(mgainer): Emit warning counter here if we don't grok
            # the response type.  We will need to cope with Oppia and
            # XBlocks responses.  Do that in a follow-on CL.

    @staticmethod
    def reduce(key, answers_and_score_list):
        correct_answers = {}
        incorrect_answers = {}
        unit_id, sequence, question_id, question_type = (
            StudentAnswersStatsGenerator.parse_key(key))
        unit_id = int(unit_id)
        question_id = long(question_id)

        for packed_data in answers_and_score_list:
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
            if not isinstance(answer, basestring):
                answer = str(answer)  # Convert numbers to strings.
            return ({'unit_id': str(unit_id),
                     'sequence': sequence,
                     'question_id': str(question_id),
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

            total_other_incorrect = 0
            for count, _ in sorted_incorrect[MAX_INCORRECT_REPORT:]:
                total_other_incorrect += count
            if total_other_incorrect:
                yield(build_reduce_dict(unit_id, sequence, question_id, False,
                                        'Other Incorrect Answers',
                                        total_other_incorrect))


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
    def get_schema(cls, unused_app_context, unused_catch_and_log,
                   unused_source_context):
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
    def exportable(cls):
        return True

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log,
                   unused_source_context):
        reg = schema_fields.FieldRegistry(
            'Course Questions',
            description='Facts about each usage of each question in a course.')
        reg.add_property(schema_fields.SchemaField(
            'question_id', 'Question ID', 'string',
            description='ID of question.  Key to models.QuestionDAO'))
        reg.add_property(schema_fields.SchemaField(
            'description', 'Description', 'string',
            description='User-entered description of question.'))
        reg.add_property(schema_fields.SchemaField(
            'text', 'Text', 'string',
            description='Text of the question.'))

        # pylint: disable=unused-variable
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
                'question_id': str(question.id),
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
    def exportable(cls):
        return True

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log,
                   unused_source_context):
        # NOTE: maintain members in parallel with build_reduce_dict() above.
        reg = schema_fields.FieldRegistry(
            'Units',
            description='Units (units, assessments, links) in a course')
        reg.add_property(schema_fields.SchemaField(
            'unit_id', 'Unit ID', 'string',
            description='ID of unit in which question appears.  Key to Unit'))
        reg.add_property(schema_fields.SchemaField(
            'now_available', 'Now Available', 'boolean',
            description='Whether the unit is publicly available'))
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
            'props', 'Properties', 'string',
            description='Site-specific additional properties added to unit'))
        reg.add_property(schema_fields.SchemaField(
            'weight', 'Weight', 'number',
            description='Weight to give to the unit when scoring.'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def fetch_values(cls, app_context, unused_source_context, unused_schema,
                     unused_catch_and_log, unused_page_number):

        # Look up questions from DB.
        units = []
        course = courses.Course(None, app_context=app_context)
        for unit in course.get_units():
            units.append({
                'unit_id': str(unit.unit_id),
                'type': unit.type,
                'title': unit.title,
                'release_date': unit.release_date,
                'now_available': course.is_unit_available(unit),
                'props': str(unit.properties),
                'weight': float(unit.weight)
                })
        return units, 0
