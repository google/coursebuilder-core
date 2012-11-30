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
# @author: pgbovine@google.com (Philip Guo)


# Stores the assessment data in the student database entry
# and returns the (possibly-modified) assessment type,
# which the caller can use to render an appropriate response page.
#
# (caller must call student.put() to commit)
#
# FIXME: Course creators can edit this code to implement
#        custom assessment scoring and storage behavior
def storeAssessmentData(student, assessment_type, score, answer):
  # TODO: Note that the latest version of answers are always saved,
  # but scores are only saved if they're higher than the previous
  # attempt.  This can lead to unexpected analytics behavior, so we
  # should resolve this somehow.
  setAssessmentAnswer(student, assessment_type, answer)
  existing_score = getAssessmentScore(student, assessment_type)
  # remember to cast to int for comparison
  if (existing_score is None) or (score > int(existing_score)):
    setAssessmentScore(student, assessment_type, score)

  # special handling for computing final score:
  if assessment_type == 'postcourse':
    midcourse_score = getAssessmentScore(student, 'midcourse')
    if midcourse_score is None:
      midcourse_score = 0
    else:
      midcourse_score = int(midcourse_score)

    if existing_score is None:
      postcourse_score = score
    else:
      postcourse_score = int(existing_score)
      if score > postcourse_score:
        postcourse_score = score

    # Calculate overall score based on a formula
    overall_score = int((0.30*midcourse_score) + (0.70*postcourse_score))

    # TODO: this changing of assessment_type is ugly ...
    if overall_score >= 70:
      assessment_type = 'postcourse_pass'
    else:
      assessment_type = 'postcourse_fail'
    setMetric(student, 'overall_score', overall_score)

  return assessment_type

# TODO: perhaps refactor everything below into a JSON format stored in a
# single StringProperty rather than using a StringListProperty

# returns a dict where the key is the assessment/summary name,
# and the value is the assessment/summary score (if available)
def getAllScores(student):
  ret = {}
  for e in student.scores + student.metrics:
    k, v = getKvPair(e)
    ret[k] = v
  return ret 

def getKvPair(kv_string):
  assert '=' in kv_string
  ind = kv_string.index('=')
  key = kv_string[:ind]
  value = kv_string[ind+1:]
  return (key, value)

def makeKvPair(key, value):
  assert '=' not in key
  return key + '=' + str(value)

def getEltWithKey(lst, my_key):
  for e in lst:
    key, value = getKvPair(e)
    if key == my_key:
      return e
  return None

def listGet(lst, my_key):
  elt = getEltWithKey(lst, my_key)
  if elt:
    key, value = getKvPair(elt)
    assert key == my_key
    return value
  else:
    return None

def listSet(lst, my_key, my_value):
  # don't insert duplicates
  existing_elt = getEltWithKey(lst, my_key)
  if existing_elt:
    lst.remove(existing_elt)
  lst.append(makeKvPair(my_key, my_value))


# returns answer as a string or None if not found
def getAssessmentAnswer(student, assessment_name):
  return listGet(student.answers, assessment_name)

# (caller must call student.put() to commit)
def setAssessmentAnswer(student, assessment_name, answer):
  listSet(student.answers, assessment_name, answer)

# returns score as a string or None if not found
# (caller must cast appropriately)
def getAssessmentScore(student, assessment_name):
  return listGet(student.scores, assessment_name)

# (caller must call student.put() to commit)
def setAssessmentScore(student, assessment_name, score):
  listSet(student.scores, assessment_name, score)

# returns value as a string or None if not found
# (caller must cast appropriately)
def getMetric(student, metric_name):
  return listGet(student.metrics, metric_name)

# (caller must call student.put() to commit)
def setMetric(student, metric_name, data):
  listSet(student.metrics, metric_name, data)
