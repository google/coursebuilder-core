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
import datetime

from mapreduce import context

from common import schema_fields
from common import tags
from models import courses
from models import data_sources
from models import entities
from models import event_transforms
from models import jobs
from models import models
from models import transforms
from tools import verify

from google.appengine.ext import db

MAX_INCORRECT_REPORT = 5


class QuestionAnswersEntity(entities.BaseEntity):
    """Student answers to individual questions."""

    data = db.TextProperty(indexed=False)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))


class RawAnswersGenerator(jobs.MapReduceJob):
    """Extract answers from all event types into QuestionAnswersEntity table."""

    @staticmethod
    def get_description():
        return 'question answers'

    @staticmethod
    def entity_class():
        return models.EventEntity

    def build_additional_mapper_params(self, app_context):
        return {
            'questions_by_usage_id': (
                event_transforms.get_questions_by_usage_id(app_context)),
            'group_to_questions': (
                event_transforms.get_group_to_questions())
            }

    @staticmethod
    def map(event):
        """Extract question responses from all event types providing them."""

        if event.source not in (
            'submit-assessment',
            'attempt-lesson',
            'tag-assessment'):
            return

        # Fetch global params set up in build_additional_mapper_params(), above.
        params = context.get().mapreduce_spec.mapper.params
        questions_info = params['questions_by_usage_id']
        group_to_questions = params['group_to_questions']

        timestamp = int(
            (event.recorded_on - datetime.datetime(1970, 1, 1)).total_seconds())
        content = transforms.loads(event.data)

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
                    questions_info, answer_data, timestamp)

        elif event.source == 'attempt-lesson':
            # Very odd that the version should be in the answers map....
            version = content.get('answers', {}).get('version')
            if version == '1.5':
                answers = event_transforms.unpack_student_answer_1_5(
                    questions_info, content, timestamp)

        elif event.source == 'tag-assessment':
            answers = event_transforms.unpack_check_answers(
                content, questions_info, group_to_questions, timestamp)

        yield (event.user_id, [list(answer) for answer in answers])

    @staticmethod
    def reduce(key, answers_lists):
        """Does not produce output to Job.  Instead, stores values to DB."""

        answers = []
        for data in answers_lists:
            answers += ast.literal_eval(data)
        data = transforms.dumps(answers)
        QuestionAnswersEntity(key_name=key, data=data).put()


class RawAnswersDataSource(data_sources.AbstractDbTableRestDataSource):
    """Make raw answers from QuestionAnswersEntity available via REST."""

    @staticmethod
    def required_generators():
        return [RawAnswersGenerator]

    @classmethod
    def get_entity_class(cls):
        return QuestionAnswersEntity

    @classmethod
    def get_name(cls):
        return 'raw_student_answers'

    @classmethod
    def get_title(cls):
        return 'Raw Student Answers'

    @classmethod
    def get_default_chunk_size(cls):
        # Selecting answers by student turns into a where-in clause, which
        # in turn turns into N different '==' filters, and AppEngine supports
        # at most 30.
        # TODO(mgainer): Do something clever so that the students who have
        # non-blank data here are returned in the earlier pages.
        # TODO(mgainer): For students with no data, return blank items so
        # we at least see rows for them in the UI, even if there are no scores.
        return 25

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log):
        reg = schema_fields.FieldRegistry(
            'Raw Student Answers',
            description='Raw data of answers to all uses of all graded '
            'questions (excludes self-check non-graded questions in lessons) '
            'in the course.')
        reg.add_property(schema_fields.SchemaField(
            'user_name', 'User ID', 'string',
            description='Name of the student for this question.'))
        reg.add_property(schema_fields.SchemaField(
            'unit_id', 'Unit ID', 'string',
            description='ID of unit or assessment for this score.'))
        reg.add_property(schema_fields.SchemaField(
            'lesson_id', 'Lesson ID', 'string', optional=True,
            description='ID of lesson for this score.'))
        reg.add_property(schema_fields.SchemaField(
            'sequence', 'Sequence', 'integer',
            description='0-based order within containing assessment/lesson.'))
        reg.add_property(schema_fields.SchemaField(
            'question_id', 'Question ID', 'string',
            description='ID of question.  Key to models.QuestionDAO'))
        reg.add_property(schema_fields.SchemaField(
            'question_type', 'Question Type', 'string',
            description='Kind of question.  E.g., "SaQuestion" or "McQuestion" '
            'for single-answer and multiple-choice, respectively.'))
        reg.add_property(schema_fields.SchemaField(
            'timestamp', 'Question ID', 'integer',
            description='Seconds since 1970-01-01 in GMT when answer given.'))
        reg.add_property(schema_fields.SchemaField(
            'answers', 'Answers', 'string',
            description='The answer from the student.  Note that '
            'this may be an array for questions permitting multiple answers.'))
        reg.add_property(schema_fields.SchemaField(
            'score', 'Score', 'integer',
            description='Value from the Question indicating the score for '
            'this answer or set of answers.'))
        reg.add_property(schema_fields.SchemaField(
            'tallied', 'Tallied', 'boolean',
            description='Whether the score counts towards the overall grade.  '
            'Lessons by default do not contribute to course score, but may '
            'be marked as graded.'))
        return reg.get_json_schema_dict()['properties']

    @classmethod
    def _postprocess_rows(cls, app_context, source_context, schema, log,
                          page_number, rows):
        """Unpack all responses from single student into separate rows."""

        # Fill in responses with actual student name, not just ID.
        student_ids = []
        for entity in rows:
            student_ids.append(entity.key().id_or_name())
        students = (models.Student
                    .all()
                    .filter('user_id in', student_ids)
                    .fetch(len(student_ids)))

        # Prepare to convert multiple-choice question indices to answer strings.
        mc_choices = {}
        for question in models.QuestionDAO.get_all():
            if 'choices' in question.dict:
                mc_choices[str(question.id)] = [
                    choice['text'] for choice in question.dict['choices']]

        ret = []
        for entity, student in zip(rows, students):
            raw_answers = transforms.loads(entity.data)
            answers = [event_transforms.QuestionAnswerInfo(*parts)
                       for parts in raw_answers]
            for answer in answers:
                if answer.question_id in mc_choices:
                    choices = mc_choices[answer.question_id]
                    given_answers = [choices[i] for i in answer.answers]
                else:
                    given_answers = answer.answers
                ret.append({
                    'user_id': student.user_id,
                    'user_name': student.name,
                    'unit_id': answer.unit_id,
                    'lesson_id': answer.lesson_id,
                    'sequence': answer.sequence,
                    'question_id': answer.question_id,
                    'question_type': answer.question_type,
                    'timestamp': answer.timestamp,
                    'answers': given_answers,
                    'score': answer.score,
                    'tallied': answer.tallied,
                    })
        return ret


class OrderedQuestionsDataSource(data_sources.SynchronousQuery):
    """Simple "analytic" giving names of each question, in course order.

    This class cooperates with the Jinja template in gradebook.html to
    generate the header for the Gradebook analytics sub-tab.  It also
    generates the expected list of questions, in course order.  This
    set of questions sets the order for the question responses
    provided by RawAnswersDataSource (above).

    """

    @staticmethod
    def fill_values(app_context, template_values):
        """Sets values into the dict used to fill out the Jinja template."""

        def _find_q_ids(html, groups):
            """Returns the list of question IDs referenced from rich HTML."""
            question_ids = []
            for component in tags.get_components_from_html(html):
                if component['cpt_name'] == 'question':
                    question_ids.append(int(component['quid']))
                elif component['cpt_name'] == 'question-group':
                    for question_id in groups[int(component['qgid'])]:
                        question_ids.append(int(question_id))
            return question_ids

        def _look_up_questions(questions, question_ids):
            """Build a dict used to build HTML for one column for one question.

            Args:
              questions: Map from question ID to QuestionDAO
              question_ids: Set of IDS for which we want to build helper dicts.
            Returns:
              An array of dicts, one per question named in question_ids.
            """
            ret = []

            for qid in list(question_ids):
                if qid not in questions:
                    question_ids.remove(qid)
                    continue
                ret.append({
                    'id': qid,
                    'description': questions[qid],
                    'href': 'dashboard?action=edit_question&key=%s' % qid,
                })
            return ret

        def _q_key(unit_id, lesson_id, question_id):
            return '%s.%s.%s' % (unit_id, lesson_id or 'null', question_id)

        def _add_assessment(unit):
            q_ids = _find_q_ids(unit.html_content, groups)
            return (
                [_q_key(unit.unit_id, None, q_id) for q_id in q_ids],
                {
                    'unit_id': None,
                    'title': None,
                    'questions': _look_up_questions(questions, q_ids)
                })

        def _add_sub_assessment(unit, assessment):
            q_ids = _find_q_ids(assessment.html_content, groups)
            return (
                [_q_key(assessment.unit_id, None, q_id) for q_id in q_ids],
                {
                    'href': 'unit?unit=%s&assessment=%s' % (
                        unit.unit_id, assessment.unit_id),
                    'unit_id': assessment.unit_id,
                    'title': assessment.title,
                    'questions': _look_up_questions(questions, q_ids),
                    'tallied': True,
                })

        def _add_lesson(unit, lesson):
            q_ids = _find_q_ids(lesson.objectives, groups)
            return (
                [_q_key(unit.unit_id, lesson.lesson_id, qid) for qid in q_ids],
                {
                    'href': 'unit?unit=%s&lesson=%s' % (
                        unit.unit_id, lesson.lesson_id),
                    'lesson_id': lesson.lesson_id,
                    'title': lesson.title,
                    'questions': _look_up_questions(questions, q_ids),
                    'tallied': lesson.scored,
                })

        def _count_colspans(units):
            for unit in units:
                unit_colspan = 0
                for item in unit['contents']:
                    # answer/score for each question, plus subtotal for section.
                    item['colspan'] = len(item['questions']) * 2
                    unit_colspan += item['colspan']

                # If a unit contains more than one sub-unit, we need a subtotal
                # column.
                if len(unit['contents']) > 1:
                    for item in unit['contents']:
                        if item['tallied']:
                            item['colspan'] += 1
                            unit_colspan += 1
                # +1 for unit total column
                unit['colspan'] = unit_colspan + 1

        course = courses.Course(None, app_context)
        questions = {q.id: q.description for q in models.QuestionDAO.get_all()}
        groups = {
            g.id: g.question_ids for g in models.QuestionGroupDAO.get_all()}
        units = []
        question_keys = []

        # Walk through the course in display order, gathering all items
        # that may contain questions.  This is used to build up the HTML
        # table headers for display.
        for unit in course.get_units():

            # Skip contained pre/post assessments; these will be done in their
            # containing unit.
            if course.get_parent_unit(unit.unit_id):
                continue
            # Only deal with known unit types
            if unit.type == verify.UNIT_TYPE_ASSESSMENT:
                href = 'assessment?name=%s' % unit.unit_id
            elif unit.type == verify.UNIT_TYPE_UNIT:
                href = 'unit?unit=%s' % unit.unit_id,
            else:
                continue

            unit_contents = []
            if unit.type == verify.UNIT_TYPE_ASSESSMENT:
                q_keys, contents = _add_assessment(unit)
                if q_keys:
                    question_keys += q_keys + ['subtotal']
                    unit_contents.append(contents)
            if unit.pre_assessment:
                assessment = course.find_unit_by_id(unit.pre_assessment)
                if assessment:
                    q_keys, contents = _add_sub_assessment(unit, assessment)
                    if q_keys:
                        question_keys += q_keys + ['subtotal']
                        unit_contents.append(contents)
            for lesson in course.get_lessons(unit.unit_id):
                q_keys, contents = _add_lesson(unit, lesson)
                if q_keys:
                    question_keys += q_keys
                    if lesson.scored:
                        question_keys += ['subtotal']
                    unit_contents.append(contents)
            if unit.post_assessment:
                assessment = course.find_unit_by_id(unit.post_assessment)
                if assessment:
                    q_keys, contents = _add_sub_assessment(unit, assessment)
                    if q_keys:
                        question_keys += q_keys + ['subtotal']
                        unit_contents.append(contents)

            if unit_contents:
                units.append({
                    'href': href,
                    'unit_id': unit.unit_id,
                    'title': unit.title,
                    'contents': unit_contents,
                    })

                # If there is only one sub-component within the unit, pop off
                # the 'subtotal' column.
                if len(unit_contents) == 1:
                    question_keys.pop()
                question_keys.append('total')

        _count_colspans(units)
        template_values['units'] = units
        template_values['gradebook_js_vars'] = transforms.dumps(
            {'question_keys': question_keys})


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
                event_transforms.get_questions_by_usage_id(app_context))
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
        all_answers = transforms.loads(student_answers.data)
        for unit_id, unit_responses in all_answers.items():

            # Is this a CourseBuilder Question/QuestionGroup set of answers?
            if ('containedTypes' in unit_responses and
                unit_responses['version'] == '1.5'):
                for answer in event_transforms.unpack_student_answer_1_5(
                    questions_by_usage_id, unit_responses, timestamp=0):
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
