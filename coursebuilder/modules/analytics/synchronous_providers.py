# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Provide data sources performing synchronous (non-paginated) reads."""

__author__ = 'Sean Lip (sll@google.com)'

import logging
import urlparse

from common import safe_dom
from models import courses
from models import data_sources
from models import jobs
from models import progress
from models import transforms
from models import utils as models_utils
from models.models import EventEntity
from models.models import Student
from models.models import StudentPropertyEntity


class StudentEnrollmentAndScoresGenerator(jobs.DurableJob):
    """A job that computes student statistics."""

    @staticmethod
    def get_description():
        return 'student enrollment and scores'

    class ScoresAggregator(object):
        """Aggregates scores statistics."""

        def __init__(self):
            # We store all data as tuples keyed by the assessment type name.
            # Each tuple keeps:
            #     (student_count, sum(score))
            self.name_to_tuple = {}

        def visit(self, student):
            if student.scores:
                scores = transforms.loads(student.scores)
                for key in scores.keys():
                    if key in self.name_to_tuple:
                        count = self.name_to_tuple[key][0]
                        score_sum = self.name_to_tuple[key][1]
                    else:
                        count = 0
                        score_sum = 0
                    self.name_to_tuple[key] = (
                        count + 1, score_sum + float(scores[key]))

    class EnrollmentAggregator(object):
        """Aggregates enrollment statistics."""

        def __init__(self):
            self.enrolled = 0
            self.unenrolled = 0

        def visit(self, student):
            if student.is_enrolled:
                self.enrolled += 1
            else:
                self.unenrolled += 1

    def run(self):
        """Computes student statistics."""
        enrollment = self.EnrollmentAggregator()
        scores = self.ScoresAggregator()
        mapper = models_utils.QueryMapper(
            Student.all(), batch_size=500, report_every=1000)

        def map_fn(student):
            enrollment.visit(student)
            scores.visit(student)

        mapper.run(map_fn)

        data = {
            'enrollment': {
                'enrolled': enrollment.enrolled,
                'unenrolled': enrollment.unenrolled},
            'scores': scores.name_to_tuple}

        return data


class StudentEnrollmentAndScoresSource(data_sources.SynchronousQuery):
    """Shows student enrollment analytics on the dashboard."""

    @staticmethod
    def required_generators():
        return [StudentEnrollmentAndScoresGenerator]

    @staticmethod
    def fill_values(app_context, template_values, job):
        stats = transforms.loads(job.output)

        course = courses.Course(None, app_context)

        template_values['enrolled'] = stats['enrollment']['enrolled']
        template_values['unenrolled'] = stats['enrollment']['unenrolled']
        scores = []
        total_records = 0
        for key, value in stats['scores'].items():
            total_records += value[0]
            avg = round(value[1] / value[0], 1) if value[0] else 0

            assessment = course.find_unit_by_id(key)
            if assessment:
                title = assessment.title
            else:
                title = "Assessment {} (deleted)".format(key)

            record = {'key': key, 'completed': value[0], 'avg': avg,
                'title':title}
            scores.append(record)
        template_values['scores'] = scores
        template_values['total_records'] = total_records


class StudentProgressStatsGenerator(jobs.DurableJob):
    """A job that computes student progress statistics."""

    @staticmethod
    def get_description():
        return 'student progress'

    class ProgressAggregator(object):
        """Aggregates student progress statistics."""

        def __init__(self, course):
            self.progress_data = {}
            self._tracker = progress.UnitLessonCompletionTracker(course)

        def visit(self, student_property):
            if (student_property.value and
                student_property.name ==
                progress.UnitLessonCompletionTracker.PROPERTY_KEY):
                entity_scores = transforms.loads(student_property.value)
                for entity in entity_scores:
                    entity_score = self.progress_data.get(
                        entity, {'progress': 0, 'completed': 0})
                    if self._tracker.determine_if_composite_entity(entity):
                        if (entity_scores[entity] ==
                            self._tracker.IN_PROGRESS_STATE):
                            entity_score['progress'] += 1
                        elif (entity_scores[entity] ==
                              self._tracker.COMPLETED_STATE):
                            entity_score['completed'] += 1
                    else:
                        if entity_scores[entity] != 0:
                            entity_score['completed'] += 1
                    self.progress_data[entity] = entity_score

    def __init__(self, app_context):
        super(StudentProgressStatsGenerator, self).__init__(app_context)
        self._course = courses.Course(None, app_context)

    def run(self):
        """Computes student progress statistics."""
        student_progress = self.ProgressAggregator(self._course)
        mapper = models_utils.QueryMapper(
            StudentPropertyEntity.all(), batch_size=500, report_every=1000)
        mapper.run(student_progress.visit)
        return student_progress.progress_data


class StudentProgressStatsSource(data_sources.SynchronousQuery):
    """Shows student progress analytics on the dashboard."""

    @staticmethod
    def required_generators():
        return [StudentProgressStatsGenerator]

    @staticmethod
    def fill_values(app_context, template_values, job):
        course = courses.Course(None, app_context=app_context)
        template_values['entity_codes'] = transforms.dumps(
            progress.UnitLessonCompletionTracker.EVENT_CODE_MAPPING.values())
        value = transforms.loads(job.output)
        if value:
            value = transforms.dumps(value)
        else:
            value = None
        template_values['progress'] = value

        try:
            template_values['content'] = transforms.dumps(
                progress.ProgressStats(course).compute_entity_dict(
                    'course', []))
        except IOError:
            template_values['update_message'] = safe_dom.Text(
                'This feature is supported by CB 1.3 and up.')


class QuestionStatsGenerator(jobs.DurableJob):
    """A job that computes stats for student submissions to questions."""

    @staticmethod
    def get_description():
        return 'question analysis'

    class MultipleChoiceQuestionAggregator(object):
        """Class that aggregates submissions for multiple-choice questions."""

        ATTEMPT_ACTIVITY = 'attempt-activity'
        TAG_ASSESSMENT = 'tag-assessment'
        ATTEMPT_LESSON = 'attempt-lesson'
        SUBMIT_ASSESSMENT = 'submit-assessment'
        ATTEMPT_ASSESSMENT = 'attempt-assessment'
        MC_QUESTION = 'McQuestion'
        QUESTION_GROUP = 'QuestionGroup'
        ACTIVITY_CHOICE = 'activity-choice'
        ACTIVITY_GROUP = 'activity-group'

        def __init__(self, course):
            self._course = course
            self.id_to_questions_dict = progress.UnitLessonCompletionTracker(
                course).get_id_to_questions_dict()
            self.id_to_assessments_dict = progress.UnitLessonCompletionTracker(
                course).get_id_to_assessments_dict()

        def _get_course(self):
            return self._course

        def _append_data(self, summarized_question, dict_to_update):
            # Validate the structure and content of summarized_question dict.
            if set(summarized_question.keys()) != {'id', 'score', 'answers'}:
                return
            if not isinstance(summarized_question['score'], (int, float)):
                return
            if not isinstance(summarized_question['answers'], list):
                return
            if any(not isinstance(answer, int) for answer in (
                    summarized_question['answers'])):
                return
            if summarized_question['id'] not in dict_to_update:
                return
            if max(summarized_question['answers']) >= len(
                    dict_to_update[summarized_question['id']]['answer_counts']):
                return

            # Add the summarized_question to the aggregating dict.
            q_dict = dict_to_update[summarized_question['id']]
            q_dict['score'] += summarized_question['score']
            q_dict['num_attempts'] += 1
            for choice_index in summarized_question['answers']:
                q_dict['answer_counts'][choice_index] += 1

        def _get_unit_and_lesson_id_from_url(self, url):
            url_components = urlparse.urlparse(url)
            query_dict = urlparse.parse_qs(url_components.query)

            if 'unit' not in query_dict:
                return None, None

            unit_id = query_dict['unit'][0]
            lesson_id = None
            if 'lesson' in query_dict:
                lesson_id = query_dict['lesson'][0]
            else:
                lessons = self._get_course().get_lessons(unit_id)
                lesson_id = lessons[0].lesson_id if lessons else None

            return unit_id, lesson_id

        def _summarize_multiple_questions(self, data, id_prefix):
            """Helper method that summarizes events from a list of questions.

            Args:
                data: data dict from event_entity['data'].
                id_prefix: str. Questions in lessons have 'u.#.l.#' formatted
                    prefix representing the unit and lesson id, and questions
                    in assessments have 's.#' formatted prefix representing
                    the assessment id.

            Returns:
                A list of dicts. Each of the dicts in the output list has the
                following keys: ['id', 'score', 'answers'].
            """
            type_info_dict = data['containedTypes']
            questions_list = []

            for instanceid, type_info in type_info_dict.iteritems():
                if isinstance(type_info, list):
                    # This is a question group.
                    mc_indices = [i for i in xrange(len(type_info))
                                  if type_info[i] == self.MC_QUESTION]
                    questions_list += [{
                        'id': '%s.c.%s.i.%s' % (id_prefix, instanceid, index),
                        'score': data['individualScores'][instanceid][index],
                        'answers': data['answers'][instanceid][index]
                    } for index in mc_indices if (
                        data['answers'][instanceid][index])]

                elif (type_info == self.MC_QUESTION and
                      data['answers'][instanceid]):
                    # This is an individual multiple-choice question.
                    questions_list += [{
                        'id': '%s.c.%s' % (id_prefix, instanceid),
                        'score': data['individualScores'][instanceid],
                        'answers': data['answers'][instanceid]
                    }]

            return questions_list

        def _get_questions_from_attempt_activity(self, event_data):
            """Summarizes activity event data into a list of dicts.

            Args:
                event_data: data dict from event_entity['data'].

            Returns:
                List of dicts. Each of the dicts in the output list has the
                following keys: ['id', 'score', 'answers'].
            """
            unit_id, lesson_id = self._get_unit_and_lesson_id_from_url(
                event_data['location'])
            if unit_id is None or lesson_id is None:
                return []

            if (event_data['type'] == self.ACTIVITY_CHOICE and
                event_data['value'] is not None):
                return [{
                    'id': 'u.%s.l.%s.b.%s' % (
                        unit_id, lesson_id, event_data['index']),
                    'score': 1.0 if event_data['correct'] else 0.0,
                    'answers': [event_data['value']]
                }]
            elif event_data['type'] == self.ACTIVITY_GROUP:
                block_id = event_data['index']

                return [{
                    'id': 'u.%s.l.%s.b.%s.i.%s' % (
                        unit_id, lesson_id, block_id, answer['index']),
                    'score': 1.0 if answer['correct'] else 0.0,
                    'answers': answer['value']
                } for answer in event_data['values'] if answer['value']]
            else:
                return []

        def _get_questions_from_tag_assessment(self, event_data):
            """Summarizes assessment tag event data into a list of dicts.

            Args:
                event_data: data dict from event_entity['data'].

            Returns:
                List of dicts. Each of the dicts in the output list has the
                following keys: ['id', 'score', 'answers'].
            """
            unit_id, lesson_id = self._get_unit_and_lesson_id_from_url(
                event_data['location'])
            if unit_id is None or lesson_id is None:
                return []

            if event_data['type'] == self.QUESTION_GROUP:
                mc_indices = [
                    i for i in xrange(len(event_data['containedTypes']))
                    if event_data['containedTypes'][i] == self.MC_QUESTION]
                return [{
                    'id': 'u.%s.l.%s.c.%s.i.%s' % (
                        unit_id, lesson_id, event_data['instanceid'], index),
                    'score': event_data['individualScores'][index],
                    'answers': event_data['answer'][index]
                } for index in mc_indices if event_data['answer'][index]]
            elif (event_data['type'] == self.MC_QUESTION and
                  event_data['answer']):
                # This is a single multiple-choice question.
                return [{
                    'id': 'u.%s.l.%s.c.%s' % (
                        unit_id, lesson_id, event_data['instanceid']),
                    'score': event_data['score'],
                    'answers': event_data['answer']
                }]
            else:
                return []

        def _get_questions_from_attempt_lesson(self, event_data):
            """Summarizes lesson attempt event data into a list of dicts.

            Args:
                event_data: data dict from event_entity['data'].

            Returns:
                List of dicts. Each of the dicts in the output list has the
                following keys: ['id', 'score', 'answers'].
            """
            unit_id, lesson_id = self._get_unit_and_lesson_id_from_url(
                event_data['location'])
            if unit_id is None or lesson_id is None:
                return []

            return self._summarize_multiple_questions(
                event_data, 'u.%s.l.%s' % (unit_id, lesson_id))

        def _get_questions_from_submit_and_attempt_assessment(self, event_data):
            """Summarizes assessment submission event data into a list of dicts.

            Args:
                event_data: data dict from event_entity['data'].

            Returns:
                List of dicts. Each of the dicts in the output list has the
                following keys: ['id', 'score', 'answers'].
            """
            if not event_data['type'].startswith('assessment-'):
                return []
            assessment_id = event_data['type'][len('assessment-'):]

            values = event_data['values']
            if isinstance(values, list):
                # This is a v1.4 (or older) assessment.
                mc_indices = [i for i in xrange(len(values))
                              if values[i]['type'] == 'choices']
                return [{
                    'id': 's.%s.i.%s' % (assessment_id, index),
                    'score': 1.0 if values[index]['correct'] else 0.0,
                    'answers': [values[index]['value']]
                } for index in mc_indices if values[index]['value'] is not None]
            elif isinstance(values, dict):
                # This is a v1.5 assessment.
                return self._summarize_multiple_questions(
                    values, 's.%s' % assessment_id)
            else:
                return []

        def _process_event(self, source, data):
            """Returns a list of questions that correspond to the event."""
            question_list = []

            try:
                if source == self.ATTEMPT_ACTIVITY:
                    question_list = self._get_questions_from_attempt_activity(
                        data)
                elif source == self.TAG_ASSESSMENT:
                    question_list = self._get_questions_from_tag_assessment(
                        data)
                elif source == self.ATTEMPT_LESSON:
                    question_list = self._get_questions_from_attempt_lesson(
                        data)
                elif (source == self.SUBMIT_ASSESSMENT or
                      source == self.ATTEMPT_ASSESSMENT):
                    question_list = (
                        self._get_questions_from_submit_and_attempt_assessment(
                            data))
            except Exception as e:  # pylint: disable=broad-except
                logging.error(
                    'Failed to process question analytics event: '
                    'source %s, data %s, error %s', source, data, e)

            return question_list

        def visit(self, event_entity):
            """Records question data from given event_entity."""
            if not event_entity or not event_entity.source:
                return

            try:
                data = transforms.loads(event_entity.data)
            except Exception:  # pylint: disable=broad-except
                return

            # A list of dicts. Each dict represents a question instance and has
            # the following keys: ['id', 'score', 'answers']. Note that a
            # single event may correspond to multiple question instance dicts.
            question_list = self._process_event(event_entity.source, data)

            # Update the correct dict according to the event source.
            if (event_entity.source == self.SUBMIT_ASSESSMENT or
                event_entity.source == self.ATTEMPT_ASSESSMENT):
                dict_to_update = self.id_to_assessments_dict
            else:
                dict_to_update = self.id_to_questions_dict

            for summarized_question in question_list:
                self._append_data(summarized_question, dict_to_update)

    def __init__(self, app_context):
        super(QuestionStatsGenerator, self).__init__(app_context)
        self._course = courses.Course(None, app_context)

    def run(self):
        """Computes submitted question answers statistics."""
        question_stats = self.MultipleChoiceQuestionAggregator(self._course)
        mapper = models_utils.QueryMapper(
            EventEntity.all(), batch_size=500, report_every=1000)
        mapper.run(question_stats.visit)
        return (question_stats.id_to_questions_dict,
                question_stats.id_to_assessments_dict)


class QuestionStatsSource(data_sources.SynchronousQuery):
    """Shows statistics on the dashboard for students' answers to questions."""

    @staticmethod
    def required_generators():
        return [QuestionStatsGenerator]

    @staticmethod
    def fill_values(app_context, template_values, job):
        # pylint: disable=unpacking-non-sequence
        accumulated_question_answers, accumulated_assessment_answers = (
            transforms.loads(job.output))

        template_values['accumulated_question_answers'] = transforms.dumps(
            accumulated_question_answers)
        template_values['accumulated_assessment_answers'] = transforms.dumps(
            accumulated_assessment_answers)
