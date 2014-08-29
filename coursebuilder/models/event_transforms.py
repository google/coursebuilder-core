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

import collections

import courses
from common import tags
import models

QuestionAnswerInfo = collections.namedtuple(
    'QuestionAnswerInfo',
    ['unit_id',
     'lesson_id',
     'sequence',  # 0-based index of the question within the lesson/assessment.
     'question_id',  # ID of the QuestionEntity to which this is an answer.
     'question_type',  # McQuestion, SaQuestion, etc.
     'timestamp',  # Timestamp from the event.
     'answers',  # The answer (or answers, if multiple-answer multiple-choice).
     'score',  # Unweighted score for the answer.
     # TODO(mgainer): weighted_score which is score * weights for group and
     # question usage.
     'tallied',  # Boolean: False for lessons where questions are not scored.
    ])


def unpack_student_answer_1_5(questions_info, unit_responses, timestamp):
    """Unpack JSON from event; convert to QuestionAnswerInfo objects.

    The JSON for events is unusually shaped; function regularizes it
    into plain-old-data objects.  Also translates from question-usage ID
    to unit_id/lesson_id/question_id.  (Note that this makes the reasonable
    assumption that a question will only be used once per lesson).  Note
    that this function flattens question groups, unpacking everything as
    a single array of questions.

    Args:
      questions_info: A map from question usage ID to unit/lesson/question IDs.
        Generate this by calling get_questions_by_usage_id().
      unit_responses: The user's responses.  Obtain this by unpacking an
        event of type 'submit-assessment' and picking out the 'values' item,
        or an event of type 'attempt-lesson' and picking out 'answers'.
      timestamp: Timestamp from the event.  Value is copied into the
        results, but not otherwise used.
    Returns:
      An array of QuestionAnswerInfo corresponding to the answers
      given by the student, as recorded in the submitted event.
    """

    ret = []
    contained_types = unit_responses['containedTypes']

    for usage_id, answers in unit_responses['answers'].items():
        if usage_id not in questions_info:
            continue  # Skip items from no-longer-present questions.

        # Note: The variable names here are in plural, but for single
        # questions, 'types', 'score' and 'answers' contain just one
        # item.  (whereas for question groups, these are all arrays)
        info = questions_info[usage_id]
        types = contained_types[usage_id]
        score = unit_responses['individualScores'][usage_id]

        # Single question - give its answer.
        if types == 'McQuestion' or types == 'SaQuestion':
            ret.append(QuestionAnswerInfo(
                info['unit'], info['lesson'], info['sequence'], info['id'],
                types, timestamp, answers, score, tallied=True))

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
                packed_ids, answers, types, score):
                _, seq, q_id = packed_id.split('.')
                ret.append(QuestionAnswerInfo(
                    info['unit'], info['lesson'], info['sequence'] + int(seq),
                    q_id, q_type, timestamp, answer, score, tallied=True))
    return ret


def unpack_check_answers(
    content, questions_info, group_to_questions, timestamp):
    """Parse check-answers submissions for ungraded questions.

    The JSON for events is unusually shaped; function regularizes it
    into plain-old-data objects.  Also translates from question-usage ID
    to unit_id/lesson_id/question_id.  (Note that this makes the reasonable
    assumption that a question will only be used once per lesson).  Note
    that this function flattens question groups, unpacking everything as
    a single array of questions.

    Args:
      content: The dict unpacked from a JSON string for an event with
        a source of 'tag-assessment'.
      questions_info: A map from question usage ID to unit/lesson/question IDs.
        Generate this by calling get_questions_by_usage_id().
      group_to_questions: A map of group ID to question ID.  Generate
        this by calling group_to_questions(), below.
      timestamp: Timestamp from the event.  Value is copied into the
        results, but not otherwise used.
    Returns:
      An array of QuestionAnswerInfo corresponding to the answers
      given by the student, as recorded in the submitted event.
    """

    qtype = content.get('type')
    if qtype == 'SaQuestion' or qtype == 'McQuestion':
        info = questions_info[content['instanceid']]
        answers = [QuestionAnswerInfo(
            info['unit'], info['lesson'], info['sequence'], info['id'], qtype,
            timestamp, content['answer'], content['score'], tallied=False)]
    elif qtype == 'QuestionGroup':
        group_usage_id = content.get('instanceid')
        info = questions_info[group_usage_id]
        qids = group_to_questions[info['id']]
        values = content.get('answer')
        scores = content.get('individualScores')
        types = content.get('containedTypes')
        answers = []
        i = 0
        for qid, val, score, qtype in zip(qids, values, scores, types):
            answers.append(QuestionAnswerInfo(
                info['unit'], info['lesson'], info['sequence'] + i, qid, qtype,
                timestamp, val, score, tallied=False))
            i += 1
    else:
        answers = []
    return answers


def _add_questions_from_html(
    questions_by_usage_id, unit_id, lesson_id, html, question_group_lengths):
    """Parse rich-text HTML and add questions found to map by ID."""

    sequence_counter = 0
    for component in tags.get_components_from_html(html):
        if component['cpt_name'] == 'question':
            questions_by_usage_id[component['instanceid']] = {
                'unit': unit_id,
                'lesson': lesson_id,
                'sequence': sequence_counter,
                'id': component['quid'],
                }
            sequence_counter += 1
        elif component['cpt_name'] == 'question-group':
            questions_by_usage_id[component['instanceid']] = {
                'unit': unit_id,
                'lesson': lesson_id,
                'sequence': sequence_counter,
                'id': component['qgid'],
                }
            sequence_counter += (
                question_group_lengths[component['qgid']])


def get_questions_by_usage_id(app_context):
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
    for unit in course.get_units():
        _add_questions_from_html(questions_by_usage_id, unit.unit_id, None,
                                 unit.html_content, question_group_lengths)
        for lesson in course.get_lessons(unit.unit_id):
            _add_questions_from_html(questions_by_usage_id, unit.unit_id,
                                     lesson.lesson_id, lesson.objectives,
                                     question_group_lengths)
    return questions_by_usage_id


def get_group_to_questions():
    ret = {}
    for group in models.QuestionGroupDAO.get_all():
        ret[str(group.id)] = [str(qid) for qid in group.question_ids]
    return ret
