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

"""Helper functions to work with various models."""

__author__ = 'Sean Lip (sll@google.com)'


import json


def get_all_scores(student):
    """Gets all score data for a student.

    Args:
        student: the student whose scores should be retrieved.

    Returns:
         a dict where the keys are the assessment/summary name, and the value
         is the assessment/summary score (if available).
    """
    if not student.scores:
        return {}
    else:
        return json.loads(student.scores)


def dict_get(dict_as_string, my_key):
    if not dict_as_string:
        return None
    else:
        return json.loads(dict_as_string).get(my_key)


def set_answer(answers, assessment_name, answer):
    """Stores the answer array for the given student and assessment.

    The caller must call answers.put() to commit.
    This does not do any type-checking on 'answer'; it just stores whatever
    is passed in.

    Args:
        answers: the StudentAnswers entity in which the answer should be stored.
        assessment_name: the name of the assessment.
        answer: an array containing the student's answers.
    """
    if not answers.data:
        score_dict = {}
    else:
        score_dict = json.loads(answers.data)
    score_dict[assessment_name] = answer
    answers.data = json.dumps(score_dict)


def get_score(student, assessment_name):
    """Gets a student's score for a particular assessment.

    The caller must cast the score appropriately.

    Args:
        student: the student whose score should be retrieved.
        assessment_name: the name of the assessment.

    Returns:
        The student's score for this assessment, or None if not found.
    """
    return dict_get(student.scores, assessment_name)


def set_score(student, assessment_name, score):
    """Stores the score for the given student and assessment.

    The caller must call student.put() to commit.
    This does not do any type-checking on 'score'; it just stores whatever
    is passed in.

    Args:
        student: the student whose answer should be stored.
        assessment_name: the name of the assessment.
        score: the student's score.
    """
    if not student.scores:
        score_dict = {}
    else:
        score_dict = json.loads(student.scores)
    score_dict[assessment_name] = score
    student.scores = json.dumps(score_dict)
