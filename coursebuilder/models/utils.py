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
#
# @author: sll@google.com (Sean Lip)


"""Helper functions to work with various models."""

import json, logging

# returns a dict where the key is the assessment/summary name,
# and the value is the assessment/summary score (if available)
def getAllScores(student):
  if not student.scores:
    return {}
  else:
    return json.loads(student.scores)

def dictGet(dict_as_string, my_key):
  if not dict_as_string:
    return None
  else:
    return json.loads(dict_as_string).get(my_key)


# returns the answer array corresponding to the given assessment, or None if
# not found
def getAnswer(student, assessment_name):
  return dictGet(student.answers, assessment_name)

# (caller must call student.put() to commit)
# NB: this does not do any type-checking on 'answer'; it just stores whatever
#     is passed in.
def setAnswer(student, assessment_name, answer):
  if not student.answers:
    score_dict = {}
  else:
    score_dict = json.loads(student.answers)
  score_dict[assessment_name] = answer
  student.answers = json.dumps(score_dict)

# returns the score corresponding to the given assessment, or None if not found
# (caller must cast appropriately)
def getScore(student, assessment_name):
  return dictGet(student.scores, assessment_name)

# (caller must call student.put() to commit)
# NB: this does not do any type-checking on 'score'; it just stores whatever
#     is passed in.
def setScore(student, assessment_name, score):
  if not student.scores:
    score_dict = {}
  else:
    score_dict = json.loads(student.scores)
  score_dict[assessment_name] = score
  student.scores = json.dumps(score_dict)

