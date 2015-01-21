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

"""Collect answers to questions from Event and provide to student aggregator."""

__author__ = ['Michael Gainer (mgainer@google.com)']

import datetime
import logging
import sys

from common import schema_fields
from models import event_transforms
from models import transforms
from modules.analytics import student_aggregate


class AnswersAggregator(student_aggregate.AbstractStudentAggregationComponent):
    """Plug-in to student aggregate for collecting answers to questions.

    This class collects all answers to all questions in a course, both on
    assessments and graded lessons as well as check-answers responses on
    un-graded lessons.
    """

    @classmethod
    def get_name(cls):
        return 'answers'

    @classmethod
    def get_event_sources_wanted(cls):
        return ['submit-assessment', 'attempt-lesson', 'tag-assessment']

    @classmethod
    def build_static_params(cls, app_context):
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

    @classmethod
    def process_event(cls, event, static_params):
        questions_info = static_params['questions_by_usage_id']
        valid_question_ids = static_params['valid_question_ids']
        group_to_questions = static_params['group_to_questions']
        assessment_weights = static_params['assessment_weights']

        timestamp = int(
            (event.recorded_on - datetime.datetime(1970, 1, 1)).total_seconds())
        content = transforms.loads(event.data)

        answers = None
        if event.source == 'submit-assessment':
            answer_data = content.get('values', {})
            # TODO(mgainer): handle assessment-as-form submissions.  Current
            # implementation only understands Question and QuestionGroup;
            # forms are simply submitted as lists of fields.
            # TODO(mgainer): Handle peer-review scoring
            if not isinstance(answer_data, dict):
                return
            version = answer_data.get('version')
            if version == '1.5':
                answers = event_transforms.unpack_student_answer_1_5(
                    questions_info, valid_question_ids, assessment_weights,
                    group_to_questions, answer_data, timestamp)
            else:
                logging.warning('Unexpected version %s in submit-assessment '
                                'event handling', version)
        elif event.source == 'attempt-lesson':
            # Very odd that the version should be in the answers map....
            version = content.get('answers', {}).get('version')
            if version == '1.5':
                answers = event_transforms.unpack_student_answer_1_5(
                    questions_info, valid_question_ids, assessment_weights,
                    group_to_questions, content, timestamp)
            else:
                logging.warning('Unexpected version %s in attempt-lesson '
                                'event handling', version)
        elif event.source == 'tag-assessment':
            answers = event_transforms.unpack_check_answers(
                content, questions_info, valid_question_ids, assessment_weights,
                group_to_questions, timestamp)
        if not answers:
            return None

        answer_dicts = []
        total_weighted_score = 0.0

        for answer in answers:
            if not isinstance(answer.answers, (tuple, list)):
                stringified_answers = [unicode(answer.answers)]
            else:
                stringified_answers = [unicode(a) for a in answer.answers]
            answer_dict = {
                'question_id': answer.question_id,
                'responses': stringified_answers,
                }
            answer_dict['score'] = float(answer.score)
            answer_dict['weighted_score'] = float(answer.weighted_score)
            total_weighted_score += answer.weighted_score
            answer_dicts.append(answer_dict)

        submission = {
            'timestamp': answers[0].timestamp,
            'answers': answer_dicts,
            }
        submission['weighted_score'] = total_weighted_score

        assessment = {
            'unit_id': str(answers[0].unit_id),
            'lesson_id': str(answers[0].lesson_id),
            'submissions': [submission],
            }
        return assessment

    @classmethod
    def produce_aggregate(cls, course, student, static_params, event_items):
        unscored_lesson_ids = [
            str(x) for x in static_params['unscored_lesson_ids']]
        assessments = []
        lookup = {}
        for item in event_items:
            key = (item['unit_id'], item['lesson_id'])
            if key not in lookup:
                assessments.append(item)
                lookup[key] = item
            else:
                lookup[key]['submissions'].extend(item['submissions'])

        # Note: need to do this the long way, since lessons may change
        # back and forth from scored to unscored.  Thus, submissions
        # will not necessarily all have scores or all not have scores.
        for assessment in assessments:
            assessment['submissions'].sort(key=lambda s: s['timestamp'])

            # Unscored lessons do not submit all questions on the page
            # all-at-once; the individual questions are submitted one-by-one
            # if/when a student clicks the "check answer" button.  This being
            # the case, there's no good meaning for min/max/etc. score.
            # (Theoretically, we could time-box and deduplicate submissions
            # that were submitted close together in time, but that work is not
            # economical.)
            if assessment['lesson_id'] not in unscored_lesson_ids:
                first_score = None
                last_score = None
                min_score = sys.maxint
                max_score = None
                for submission in assessment['submissions']:
                    if 'weighted_score' in submission:
                        score = submission['weighted_score']
                        if first_score is None:
                            first_score = score
                        last_score = score
                        min_score = min(min_score, score)
                        max_score = max(max_score, score)
                if first_score is not None:
                    assessment['first_score'] = first_score
                if last_score is not None:
                    assessment['last_score'] = last_score
                if max_score is not None:
                    assessment['max_score'] = max_score
                    assessment['min_score'] = min_score
        return {'assessments': assessments}

    @classmethod
    def get_schema(cls):
        answer = schema_fields.FieldRegistry('answer')
        answer.add_property(schema_fields.SchemaField(
            'question_id', 'Question ID', 'string'))
        answer.add_property(schema_fields.SchemaField(
            'score', 'Score', 'number', optional=True,
            description='Raw score value for this question'))
        answer.add_property(schema_fields.SchemaField(
            'weighted_score', 'Weighted Score', 'number', optional=True,
            description='Score for this question with all weights for '
            'question instance, question group, and assessment applied.'))
        answer.add_property(schema_fields.FieldArray(
            'responses', 'Responses',
            description='Responses to the question.  There may be multiple '
            'responses on questions permitting them',
            item_type=schema_fields.SchemaField('response', 'Response',
                                                 'string')))
        submission = schema_fields.FieldRegistry('sumbission')
        submission.add_property(schema_fields.SchemaField(
            'timestamp', 'Timestamp', 'timestamp'))
        submission.add_property(schema_fields.FieldArray(
            'answers', 'Answers', item_type=answer))
        submission.add_property(schema_fields.SchemaField(
            'weighted_score', 'Weighted Score', 'number', optional=True,
            description='Score for this assessment with all weights for '
            'question instance, question group, and assessment applied.  '
            'This field will be blank for answers to questions on '
            'non-scored lessons.'))

        assessment = schema_fields.FieldRegistry('assessment')
        assessment.add_property(schema_fields.SchemaField(
            'unit_id', 'Unit ID', 'string'))
        assessment.add_property(schema_fields.SchemaField(
            'lesson_id', 'Lesson ID', 'string', optional=True))
        assessment.add_property(schema_fields.FieldArray(
            'submissions', 'Submissions', item_type=submission,
            description='Each submission of an assessment.  Assessments '
            'and graded lessons will have the same list of questions in '
            'the "answers" field in each submission.  In non-graded '
            'lessons, each question is checked individually, so '
            'submissions for such lessons will have only one response in '
            'each submission.'))
        assessment.add_property(schema_fields.SchemaField(
            'min_score', 'Min Score', 'number', optional=True))
        assessment.add_property(schema_fields.SchemaField(
            'max_score', 'Max Score', 'number', optional=True))
        assessment.add_property(schema_fields.SchemaField(
            'first_score', 'First Score', 'number', optional=True))
        assessment.add_property(schema_fields.SchemaField(
            'last_score', 'Last Score', 'number', optional=True))

        assessments = schema_fields.FieldArray(
            'assessments', 'Assessments', item_type=assessment,
            description='Every submission of every assessment and lesson '
            'from this student.')
        return assessments
