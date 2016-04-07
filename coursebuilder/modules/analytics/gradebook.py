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

"""Gradebook analytic - displays answers, scores per student."""

__author__ = 'Mike Gainer (mgainer@google.com)'

import ast
import collections
import csv
import datetime
import itertools
import re
import StringIO

from mapreduce import context

from common import catch_and_log
from common import crypto
from common import schema_fields
from common import tags
from controllers import utils
from models import courses
from models import data_sources
from models import event_transforms
from models import jobs
from models import models
from models import roles
from models import transforms
from modules.analytics import filters
from modules.analytics import student_answers
from modules.student_groups import student_groups
from tools import verify
from tools.etl import etl_lib

from google.appengine.api import app_identity
from google.appengine.api import datastore
from google.appengine.ext import db

_MODE_ARG_NAME = 'mode'
_MODE_SCORES = 'scores'
_MODE_QUESTIONS = 'questions'
_MODES = [_MODE_SCORES, _MODE_QUESTIONS]

class QuestionAnswersEntity(filters.AbstractFilteredEntity):
    """Student answers to individual questions."""

    # For filtering based on student group ID.
    student_group = db.IntegerProperty(indexed=True)

    @classmethod
    def get_filters(cls):
        return [student_groups.StudentGroupFilter]

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        return db.Key.from_path(cls.kind(), transform_fn(db_key.id_or_name()))


class RawAnswersGenerator(filters.AbstractFilteredMapReduceJob):
    """Extract answers from all event types into QuestionAnswersEntity table."""

    TOTAL_STUDENTS = 'total_students'

    @staticmethod
    def get_description():
        return 'raw question answers'

    @staticmethod
    def entity_class():
        return models.EventEntity

    @staticmethod
    def result_class():
        return QuestionAnswersEntity

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

    @classmethod
    def map(cls, event):
        """Extract question responses from all event types providing them."""

        if event.source not in (
            'submit-assessment',
            'attempt-lesson',
            'tag-assessment'):
            return

        # Fetch global params set up in build_additional_mapper_params(), above.
        params = context.get().mapreduce_spec.mapper.params
        questions_info = params['questions_by_usage_id']
        valid_question_ids = params['valid_question_ids']
        group_to_questions = params['group_to_questions']
        assessment_weights = params['assessment_weights']

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
                    questions_info, valid_question_ids, assessment_weights,
                    group_to_questions, answer_data, timestamp)

        elif event.source == 'attempt-lesson':
            # Very odd that the version should be in the answers map....
            version = content.get('answers', {}).get('version')
            if version == '1.5':
                answers = event_transforms.unpack_student_answer_1_5(
                    questions_info, valid_question_ids, assessment_weights,
                    group_to_questions, content, timestamp)

        elif event.source == 'tag-assessment':
            answers = event_transforms.unpack_check_answers(
                content, questions_info, valid_question_ids, assessment_weights,
                group_to_questions, timestamp)

        yield (RawAnswersGenerator.TOTAL_STUDENTS, event.user_id)

        # Each answer is a namedtuple; convert to a list for pack/unpack
        # journey through the map/reduce shuffle stage.
        result = [list(answer) for answer in answers]
        for key in cls._generate_keys(event, event.user_id):
            yield (key, result)

    @classmethod
    def reduce(cls, keys, answers_lists):
        """Stores values to DB, and emits one aggregate: Count of students."""

        if keys == RawAnswersGenerator.TOTAL_STUDENTS:
            student_ids = set(answers_lists)
            yield (keys, len(student_ids))
            return

        answers = itertools.chain(*[ast.literal_eval(l) for l in answers_lists])
        data = transforms.dumps(list(answers))
        cls._write_entity(keys, data)


StudentPlaceholder = collections.namedtuple(
    'StudentPlaceholder', ['user_id', 'name', 'email'])


class RawAnswersDataSource(data_sources.SynchronousQuery,
                           data_sources.AbstractDbTableRestDataSource):
    """Make raw answers from QuestionAnswersEntity available via REST."""

    MAX_INTERACTIVE_DOWNLOAD_SIZE = 100

    @staticmethod
    def required_generators():
        return [RawAnswersGenerator]

    @staticmethod
    def fill_values(app_context, template_values, raw_answers_job):
        results = jobs.MapReduceJob.get_results(raw_answers_job)
        if not results:
            template_values['any_results'] = False
        else:
            template_values['any_results'] = True
            template_values['max_interactive_download_size'] = (
                RawAnswersDataSource.MAX_INTERACTIVE_DOWNLOAD_SIZE)
            results = {k: v for k, v in results}
            template_values['interactive_download_allowed'] = (
                results[RawAnswersGenerator.TOTAL_STUDENTS] <=
                RawAnswersDataSource.MAX_INTERACTIVE_DOWNLOAD_SIZE)
            template_values['course_slug'] = app_context.get_slug()
            template_values['app_id'] = (
                app_identity.get_application_id())
            template_values['hostname'] = (
                app_identity.get_default_version_hostname())

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
    def get_filters(cls):
        return QuestionAnswersEntity.get_filters()

    @classmethod
    def get_schema(cls, unused_app_context, unused_catch_and_log,
                   unused_source_context):
        reg = schema_fields.FieldRegistry(
            'Raw Student Answers',
            description='Raw data of answers to all uses of all graded '
            'questions (excludes self-check non-graded questions in lessons) '
            'in the course.')
        reg.add_property(schema_fields.SchemaField(
            'user_id', 'User ID', 'string',
            description='ID of the student providing this answer.'))
        reg.add_property(schema_fields.SchemaField(
            'user_name', 'User Name', 'string',
            description='Name of the student providing this answer.'))
        reg.add_property(schema_fields.SchemaField(
            'user_email', 'User Email', 'string',
            description='Email address of the student providing this answer.'))
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
        choice_type = schema_fields.SchemaField(
            'answer', 'Answer', 'string',
            description='An answer to the question')
        reg.add_property(schema_fields.FieldArray(
            'answers', 'Answers', item_type=choice_type,
            description='The answer from the student.  Note that '
            'this may be an array for questions permitting multiple answers.'))
        reg.add_property(schema_fields.SchemaField(
            'score', 'Score', 'number',
            description='Value from the Question indicating the score for '
            'this answer or set of answers.'))
        reg.add_property(schema_fields.SchemaField(
            'weighted_score', 'Weighted Score', 'number',
            description='Question score, multiplied by weights in '
            'containing Question Group, Assessment, etc.'))
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
        ids = []
        for entity in rows:
            ids.append(entity.primary_id)

        # Chunkify student lookups; 'in' has max of 30
        students = []
        size = datastore.MAX_ALLOWABLE_QUERIES
        for ids_chunk in [ids[i:i + size] for i in xrange(0, len(ids), size)]:
            students_chunk = (models.Student
                              .all()
                              .filter('user_id in', ids_chunk)
                              .fetch(len(ids_chunk)))
            students_by_id = {s.user_id: s for s in students_chunk}

            for student_id in ids_chunk:
                if student_id in students_by_id:
                    students += [students_by_id[student_id]]
                else:
                    students += [StudentPlaceholder(
                        student_id, '<unknown>', '<unknown>')]

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
                    given_answers = []
                    for i in answer.answers:
                        given_answers.append(
                            choices[i] if i < len(choices)
                            else '[deleted choice]')
                else:
                    given_answers = answer.answers
                    if not isinstance(given_answers, list):
                        given_answers = [given_answers]
                ret.append({
                    'user_id': student.user_id,
                    'user_name': student.name or '<blank>',
                    'user_email': student.email or '<blank>',
                    'unit_id': str(answer.unit_id),
                    'lesson_id': str(answer.lesson_id),
                    'sequence': answer.sequence,
                    'question_id': str(answer.question_id),
                    'question_type': answer.question_type,
                    'timestamp': answer.timestamp,
                    'answers': given_answers,
                    'score': float(answer.score),
                    'weighted_score': float(answer.weighted_score),
                    'tallied': answer.tallied,
                    })
        return ret


class AnswersDataSource(RawAnswersDataSource):
    """Exposes user-ID-obscured versions of all answers to all questions.

    This data source is meant to be used for aggregation or export to
    BigQuery (in contrast to RawAnswersDataSource, which should only ever
    be used within CourseBuilder, as that class exposes un-obscured user
    IDs and names).
    """

    @classmethod
    def get_name(cls):
        return 'answers'

    @classmethod
    def get_title(cls):
        return 'Answers'

    @classmethod
    def get_default_chunk_size(cls):
        return 1000

    @classmethod
    def get_schema(cls, app_context, log, source_context):
        schema = super(AnswersDataSource, cls).get_schema(app_context, log,
                                                          source_context)
        schema.pop('user_name')
        return schema

    @classmethod
    def _postprocess_rows(cls, app_context, source_context, schema, log,
                          page_number, rows):
        items = super(AnswersDataSource, cls)._postprocess_rows(
            app_context, source_context, schema, log, page_number, rows)
        for item in items:
            item.pop('user_name')
            item['user_id'] = crypto.hmac_sha_2_256_transform(
                source_context.pii_secret, item['user_id'])
        return items


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
                    qgid = int(component['qgid'])
                    if qgid in groups:
                        for question_id in groups[qgid]:
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
            return '%s.%s.%s' % (unit_id, lesson_id, question_id)

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
                        if len(item['questions']) > 1 and item['tallied']:
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
                    question_keys += q_keys
                    unit_contents.append(contents)
            if unit.pre_assessment:
                assessment = course.find_unit_by_id(unit.pre_assessment)
                if assessment:
                    q_keys, contents = _add_sub_assessment(unit, assessment)
                    if q_keys:
                        question_keys += q_keys
                        if len(q_keys) > 1:
                            question_keys += ['subtotal']
                        unit_contents.append(contents)
            for lesson in course.get_lessons(unit.unit_id):
                q_keys, contents = _add_lesson(unit, lesson)
                if q_keys:
                    question_keys += q_keys
                    if len(q_keys) > 1 and contents['tallied']:
                        question_keys += ['subtotal']
                    unit_contents.append(contents)
            if unit.post_assessment:
                assessment = course.find_unit_by_id(unit.post_assessment)
                if assessment:
                    q_keys, contents = _add_sub_assessment(unit, assessment)
                    if q_keys:
                        question_keys += q_keys
                        if len(q_keys) > 1:
                            question_keys += ['subtotal']
                        unit_contents.append(contents)

            if unit_contents:
                units.append({
                    'href': href,
                    'unit_id': unit.unit_id,
                    'title': unit.title,
                    'contents': unit_contents,
                    })

                question_keys.append('total')

        _count_colspans(units)
        template_values['units'] = units
        template_values['gradebook_js_vars'] = transforms.dumps(
            {'question_keys': question_keys})


class AbstractGradebookCsvGenerator(object):

    def __init__(self, app_context, source_context=None):
        self._app_context = app_context
        self._source_context = source_context

    def get_output(self):
        student_question_answers = self._fetch_all_question_answers()
        column_titles, ids_to_index = self._walk_course()
        answer_rows = self._reduce_answers(
            student_question_answers, ids_to_index)

        stream = StringIO.StringIO()
        csv_stream = csv.writer(stream, quoting=csv.QUOTE_MINIMAL)
        for row in [column_titles] + answer_rows:
            row = [i.encode('utf-8') if isinstance(i, unicode) else str(i)
                   for i in row]
            csv_stream.writerow(row)
        ret = stream.getvalue()
        stream.close()
        return ret

    def _fetch_all_question_answers(self):
        source_class = RawAnswersDataSource
        values = []
        chunk_size = source_class.get_default_chunk_size()
        context_class = source_class.get_context_class()
        source_context = context_class.build_blank_default({}, chunk_size)
        catch_and_log_ = catch_and_log.CatchAndLog()
        sought_page_number = 0
        with catch_and_log_.propagate_exceptions('Loading gradebook data'):
            schema = source_class.get_schema(
                self._app_context, catch_and_log, source_context)
            while True:
                data, actual_page_number = source_class.fetch_values(
                    self._app_context, source_context, schema, catch_and_log_,
                    sought_page_number)
                if actual_page_number != sought_page_number:
                    break
                values.extend(data)
                if len(data) < source_context.chunk_size:
                    break
                sought_page_number += 1
        values.sort(key=lambda x: x['user_email'])
        return values

    def _walk_course(self):
        """Traverse course, producing helper items.

        Produces ordered items for scorable course elements; these are in
        syllabus order (taking into account pre/post Assessment).

        Returns:
          A 2-tuple, containing:
          - A list of titles for things in the course that can be scored;
            this includes top-level assessments, pre/post-assessments, and
            lessons.
          - A map keyed by 2-tuple of (unit_id, lesson_id), yielding the
            index corresponding to that 2-tuple in the titles list.
            NOTE: Tuples should index starting at 1, not 0.  The 0th
            column is reserved for the email address of the student.
        """
        raise NotImplementedError()

    def _reduce_answers(self, student_question_answers, ids_to_index):
        """Iterate over student answers to produce rows for CSV output.

        Args:
          student_question_answers: Rows, as generated by
              RawAnswersDataSource._postprocess_rows.  Each row corresponds to
              one answer to one question by one student.  All answers for each
              student are guaranteed to be adjacent.  This is not a complete
              Cartesian product of students X all possible questions; only the
              questions actually answered by the student will be present.  It
              is up to the subclass to correctly place results in the (fixed-
              width) CSV rows.
          ids_to_index: As described in return value for _walk_course().
        Returns:
          An iterable of iterables.  Each iterable should provide a list of
              items for a single student, starting with the student's
              email address.
        """
        raise NotImplementedError


class GradebookGradedItemsCsvGenerator(AbstractGradebookCsvGenerator):

    def _walk_course(self):
        course = courses.Course.get(app_context=self._app_context)

        titles = ['Email']
        indices_by_unit_and_lesson = {}

        def add_index(unit_id, lesson_id):
            """Convenience function; count by 1 each addition to indices map."""
            indices_by_unit_and_lesson[(str(unit_id), str(lesson_id))] = len(
                indices_by_unit_and_lesson)

        for unit in course.get_units():
            if unit.type == verify.UNIT_TYPE_ASSESSMENT:
                if not course.get_parent_unit(unit.unit_id):
                    titles.append(unit.title)
                    add_index(unit.unit_id, None)
            elif unit.type == verify.UNIT_TYPE_UNIT:
                if unit.pre_assessment:
                    assessment = course.find_unit_by_id(unit.pre_assessment)
                    titles.append('%s: %s' % (unit.title, assessment.title))
                    add_index(assessment.unit_id, None)
                for lesson in course.get_lessons(unit.unit_id):
                    titles.append('%s: %s' % (unit.title, lesson.title))
                    add_index(unit.unit_id, lesson.lesson_id)
                if unit.post_assessment:
                    assessment = course.find_unit_by_id(unit.post_assessment)
                    titles.append('%s: %s' % (unit.title, assessment.title))
                    add_index(assessment.unit_id, None)
        return titles, indices_by_unit_and_lesson

    def _reduce_answers(self, student_question_answers, ids_to_index):
        prev_email = None
        ret = []
        for answer in student_question_answers:
            if answer['user_email'] != prev_email:
                prev_email = answer['user_email']
                answers = [answer['user_email']] + [0.0] * len(ids_to_index)
                ret.append(answers)
            index = ids_to_index[(answer['unit_id'], answer['lesson_id'])] + 1
            answers[index] += answer['weighted_score']
        return ret


class GradebookAllQuestionsCsvGenerator(AbstractGradebookCsvGenerator):

    def produce_result_rows(self, student_question_answers):
        column_titles, ids_to_index = self._walk_course()
        answer_rows = self._reduce_answers(student_question_answers,
                                           ids_to_index)
        return [column_titles] + answer_rows


    def _walk_course(self):
        template_values = {}
        OrderedQuestionsDataSource.fill_values(
            self._app_context, template_values)
        js_vars = transforms.loads(template_values['gradebook_js_vars'])
        course = courses.Course(None, app_context=self._app_context)
        questions, unused_page_number = (
            student_answers.CourseQuestionsDataSource.fetch_values(
                self._app_context, None, None, None, 0))
        question_names = {q['question_id']: q['description'] for q in questions}

        column_titles = ['Email']
        ids_to_index = {}
        question_keys = js_vars['question_keys']
        for question_key in question_keys:
            if '.' in question_key:
                unit_id, lesson_id, question_id = question_key.split('.')
                ids_to_index[(unit_id, lesson_id, question_id)] = 1 + 2 * len(
                    ids_to_index)
                question_name = question_names.get(question_id, 'UNKNOWN')
                column_titles.append(question_name + ' answer')
                column_titles.append(question_name + ' score')

        return column_titles, ids_to_index

    def _reduce_answers(self, student_question_answers, ids_to_index):
        prev_email = None
        ret = []
        for answer in student_question_answers:
            if answer['user_email'] != prev_email:
                prev_email = answer['user_email']
                answers = [answer['user_email']] + ['', 0.0] * len(ids_to_index)
                ret.append(answers)
            index = ids_to_index[
                (answer['unit_id'], answer['lesson_id'], answer['question_id'])]
            response = answer['answers']
            if len(response) == 1:
                answers[index] = response[0]
            else:
                answers[index] = str(response)
            answers[index + 1] = answer['weighted_score']
        return ret


def _generate_csv(app_context, mode):
    if mode == _MODE_SCORES:
        generator_class = GradebookGradedItemsCsvGenerator
    elif mode == _MODE_QUESTIONS:
        generator_class = GradebookAllQuestionsCsvGenerator
    else:
        raise ValueError('Mode "%s" not in %s' % (mode, ','.join(_MODES)))
    generator = generator_class(app_context)
    output = generator.get_output()
    return output


class DownloadAsCsv(etl_lib.CourseJob):
    """Use ETL framework to download gradebook data as .csv files.

    Usage:

    ./scripts/etl.sh run modules.analytics.gradebook.DownloadAsCsv \
        /the_course_name \
        appengine_instance_name \
        appengine_instance_name.appspot.com \
        --job_args='--mode=MODE --save_as=file_namne_to_save_as.csv'

    MODE can be "scores" or "questions".  "Scores" provides total scores for
    assessments and scored lessons for each student.  "Questions" gives
    the student's answer and score for each question.
    """

    def _configure_parser(self):
        self.parser.add_argument(
            '--%s' % _MODE_ARG_NAME, choices=_MODES)
        self.parser.add_argument(
            '--save_as', type=str, help='Path of the file to save output to')

    def main(self):
        app_context = self._get_app_context_or_die(
            self.etl_args.course_url_prefix)
        output = _generate_csv(app_context, self.args.mode)
        with open(self.args.save_as, 'w') as fp:
            fp.write(output)


class CsvDownloadHandler(utils.BaseHandler):

    URI = '/gradebook/csv'

    def get(self):
        if not roles.Roles.is_course_admin(self.app_context):
            self.error(401)
        mode = self.request.get(_MODE_ARG_NAME, _MODE_SCORES)
        output = _generate_csv(self.app_context, mode)
        filename = '%s_%s.csv' % (self.app_context.get_title(), mode)
        safe_filename = re.sub(r'[\"\']', '_', filename.lower())
        if isinstance(safe_filename, unicode):
            safe_filename = safe_filename.encode('utf-8')
        self.response.headers.add('Content-Type', 'text/csv')
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec19.html#sec19.5.1
        self.response.headers.add(
            'Content-Disposition',
            str('attachment; filename="%s"' % str(safe_filename)))
        self.response.write(output)
