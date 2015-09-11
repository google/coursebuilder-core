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
import logging

import courses
from common import tags
import models
from tools import verify

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
     'weighted_score',  # Score fully weighted by question instance in HTML
                        # or question usage in group and assessment (if in
                        # assessment)
     'tallied',  # Boolean: False for lessons where questions are not scored.
    ])


def _unpack_single_question_answer_1_5(
    info, types, score, assessment_weight, timestamp, answers,
    valid_question_ids):

    if info['id'] not in valid_question_ids:
        logging.info('Question with ID "%s" is no longer present; '
                     'ignoring data for it.', info['id'])
        return []

    weighted_score = score * info['weight'] * assessment_weight
    return [QuestionAnswerInfo(
        info['unit'], info['lesson'], info['sequence'], info['id'],
        types, timestamp, answers, score, weighted_score, tallied=True)]


def _unpack_question_group_answer_1_5(
    info, types, scores, assessment_weight, timestamp, answers,
    usage_id, unit_responses, group_to_questions, valid_question_ids):
    # Sometimes the event contains enough information to get the
    # question IDs in the question group directly; this happens for
    # assessments.  For graded lessons, we don't have that luxury, and
    # we need to (attempt to) rediscover the question IDs from
    # information gathered at map/reduce time.
    ret = []
    seqs = []
    q_ids = []

    if info['id'] not in group_to_questions:
        logging.info(
            'Question group with ID %s is referenced in an event, but '
            'is no longer present in the course.  Ignoring the '
            'question group answer.', info['id'])
        return []

    if usage_id in unit_responses:
        # Assessment events contain packed strings of the form
        # <question-usage-id-string>.<sequence#>.<QuestionEntity id>
        # keyed by the usage-ID string for the question group.
        # Unpack these into arrays for use below.
        packed_ids = unit_responses[usage_id].keys()
        packed_ids.sort(key=lambda packed: int(packed.split('.')[1]))
        for packed_id in packed_ids:
            _, seq, q_id = packed_id.split('.')
            seqs.append(seq)
            if q_id not in valid_question_ids:
                logging.info('Question with ID "%s" is no longer present; '
                             'ignoring it and the question group containing '
                             'it.', info['id'])
                return []
            q_ids.append(q_id)
    else:
        for seq, q_info in enumerate(group_to_questions[info['id']]):
            seqs.append(seq)
            q_id = q_info['question']
            if q_id not in valid_question_ids:
                logging.info('Question with ID "%s" is no longer present; '
                             'ignoring it and the question group containing '
                             'it.', info['id'])
                return []
            q_ids.append(q_id)

    if (len(q_ids) != len(answers) or
        len(q_ids) != len(group_to_questions[info['id']])):

        logging.info(
            'Question group usage "%s" in location "%s" has '
            'changed length since an older event was recorded; '
            'ignoring the unusable group answer.', usage_id,
            unit_responses.get('location', ''))
        return []

    for q_id, seq, answer, q_type, q_score in zip(
        q_ids, seqs, answers, types, scores):

        # Here, we are guessing at the actual weight, since the
        # weight for each question is not supplied in the event.
        # We do, however, have the question ID, so if that question
        # is still part of the question group, we can use the current
        # weight value.
        # TODO(mgainer): When we get server-side grading, this mess
        # can finally get ripped out.
        weight_in_group = 1.0
        for item in group_to_questions.get(info['id'], []):
            if item['question'] == q_id:
                weight_in_group = item['weight']

        weighted_score = q_score * weight_in_group * assessment_weight
        ret.append(QuestionAnswerInfo(
            info['unit'], info['lesson'], info['sequence'] + int(seq),
            q_id, q_type, timestamp, answer, q_score, weighted_score,
            tallied=True))
    return ret


def unpack_student_answer_1_5(questions_info, valid_question_ids,
                              assessment_weights, group_to_questions,
                              unit_responses, timestamp):
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
      assessment_weights: Map from assessment ID to weight for that assessment.
      group_to_questions: Map from question group ID to list of
        dicts holding question ID as 'question' and weight as 'weight'.
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
        if usage_id == 'version':  # Found in graded assessments.
            continue
        if usage_id not in questions_info:
            logging.info('Question or question-group ID "%s" in event is '
                         'no longer present', usage_id)
            continue  # Skip items from no-longer-present questions.

        # Note: The variable names here are in plural, but for single
        # questions, 'types', 'score' and 'answers' contain just one
        # item.  (whereas for question groups, these are all arrays)
        info = questions_info[usage_id]
        types = contained_types[usage_id]
        score = unit_responses['individualScores'][usage_id]
        unit_id = info['unit']
        assessment_weight = assessment_weights.get(str(unit_id), 1.0)

        # Single question - give its answer.
        if types == 'McQuestion' or types == 'SaQuestion':
            ret.extend(_unpack_single_question_answer_1_5(
                info, types, score, assessment_weight, timestamp, answers,
                valid_question_ids))

        # Question group. Fetch IDs of sub-questions, which are packed as
        # <group-usage-id>.<sequence>.<question-id>.
        # Order by <sequence>, which is 0-based within question-group.
        elif isinstance(types, list):
            ret.extend(_unpack_question_group_answer_1_5(
                info, types, score, assessment_weight, timestamp, answers,
                usage_id, unit_responses, group_to_questions,
                valid_question_ids))
    return ret


def unpack_check_answers(
    content, questions_info, valid_question_ids, assessment_weights,
    group_to_questions, timestamp):
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
      assessment_weights: Map from assessment ID to weight for that assessment.
      group_to_questions: A map of group ID to dicts, as follows.  Generate
        this by calling group_to_questions(), below.
        'question' -> string containing question ID.
        'weight' -> float representing the weight of that question in this group
      timestamp: Timestamp from the event.  Value is copied into the
        results, but not otherwise used.
    Returns:
      An array of QuestionAnswerInfo corresponding to the answers
      given by the student, as recorded in the submitted event.
    """

    qtype = content.get('type')
    usage_id = content['instanceid']
    if usage_id not in questions_info:
        logging.info('Question or question-group ID "%s" in event is '
                     'no longer present', usage_id)
        return []
    info = questions_info[usage_id]
    assessment_weight = assessment_weights.get(info['unit'], 1.0)

    if qtype == 'SaQuestion' or qtype == 'McQuestion':
        if info['id'] not in valid_question_ids:
            logging.info('Question with ID "%s" is no longer present; '
                         'ignoring data for it.', info['id'])
            return []
        score = content.get('score', 0.0)
        weighted_score = score * info['weight'] * assessment_weight
        answers = [QuestionAnswerInfo(
            info['unit'], info['lesson'], info['sequence'], info['id'], qtype,
            timestamp, content['answer'], score, weighted_score, tallied=False)]
    elif qtype == 'QuestionGroup':
        values = content.get('answer')
        scores = content.get('individualScores')
        types = content.get('containedTypes')

        # Here, we have to hope that the length and order of questions within
        # a group has not changed since the event was recorded, as the events
        # do not record the question ID within the group.  We just assume that
        # the index at the time the check-answer event was recorded is the
        # same as in the question group currently.
        # TODO(mgainer): When we get server-side grading, buff this up.
        group_id = questions_info[usage_id]['id']
        if group_id not in group_to_questions:
            logging.info(
                'Question group with ID %s is referenced in an event, but '
                'is no longer present in the course.  Ignoring the unusable '
                'question group answer.', group_id)
            return []

        q_infos = group_to_questions.get(group_id, [])
        if len(q_infos) != len(values):
            logging.info('Ignoring event for question group "%s": '
                         'This group currently has length %d, '
                         'but event has length %d.', usage_id,
                         len(q_infos), len(values))
            return []

        answers = []
        i = 0
        for q_info, val, score, qtype in zip(q_infos, values, scores, types):
            weighted_score = score * q_info['weight'] * assessment_weight
            answers.append(QuestionAnswerInfo(
                info['unit'], info['lesson'], info['sequence'] + i,
                q_info['question'], qtype, timestamp, val, score,
                weighted_score, tallied=False))
            i += 1
    else:
        logging.warning('Not handling unknown question or group type "%s"',
                        qtype)
        answers = []
    return answers


def _add_questions_from_html(
    questions_by_usage_id, unit_id, lesson_id, html, question_group_lengths):
    """Parse rich-text HTML and add questions found to map by ID."""

    sequence_counter = 0
    for component in tags.get_components_from_html(html):
        if component['cpt_name'] == 'question':
            weight = 1.0
            if 'weight' in component and component['weight'] != '':
                try:
                    weight = float(component['weight'])
                except ValueError:
                    logging.warning(
                        'Weight "%s" is not a number; using 1.0 instead.',
                        component['weight'])

            questions_by_usage_id[component['instanceid']] = {
                'unit': unit_id,
                'lesson': lesson_id,
                'sequence': sequence_counter,
                'id': component['quid'],
                'weight': weight,
                }
            sequence_counter += 1
        elif component['cpt_name'] == 'question-group':
            questions_by_usage_id[component['instanceid']] = {
                'unit': unit_id,
                'lesson': lesson_id,
                'sequence': sequence_counter,
                'id': component['qgid'],
                }
            if component['qgid'] in question_group_lengths:
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


def get_assessment_weights(app_context):
    ret = {}
    course = courses.Course(None, app_context)
    for unit in course.get_units():
        if unit.type == verify.UNIT_TYPE_ASSESSMENT:
            ret[str(unit.unit_id)] = float(unit.weight)
    return ret


def get_group_to_questions():
    ret = {}
    for group in models.QuestionGroupDAO.get_all():
        items = group.items
        for element in items:
            element['question'] = str(element['question'])
            weight = 1.0
            if 'weight' in element and element['weight'] != '':
                try:
                    weight = float(element['weight'])
                except ValueError:
                    logging.warning(
                        'Weight "%s" is not a number; using 1.0 instead.',
                        element['weight'])
            element['weight'] = weight
        ret[str(group.id)] = items
    return ret


def get_unscored_lesson_ids(app_context):
    ret = []
    for lesson in courses.Course(None, app_context).get_lessons_for_all_units():
        if not lesson.scored:
            ret.append(lesson.lesson_id)
    return ret

def get_valid_question_ids():
    ret = []
    for question in models.QuestionDAO.get_all():
        ret.append(str(question.id))
    return ret
