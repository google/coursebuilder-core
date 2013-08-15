/*
  Copyright 2013 Google Inc. All Rights Reserved.

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
*/

QUESTION_TYPES = {
  MC_QUESTION: 'McQuestion',
  SA_QUESTION: 'SaQuestion',
  QUESTION_GROUP: 'QuestionGroup'
}

/**
 * Base class for rendering questions.
 */
function BaseQuestion(el, questionData, messages, componentAudit) {
  this.el = el;
  this.id = this.el.attr('id');
  this.data = questionData[this.id];
  this.scored = questionData.scored;
  this.messages = messages;
  this.componentAudit = componentAudit;
}
BaseQuestion.bindSubclass = function(subclass) {
  var tmp = function() {};
  tmp.prototype = BaseQuestion.prototype;
  subclass.prototype = new tmp();
  subclass.prototype.constructor = subclass;
}
BaseQuestion.prototype.getMessageAboutScore = function(score) {
  if (score > 0.99) {
    return this.messages.correctAnswer;
  } else if (score < 0.01) {
    return this.messages.incorrectAnswer;
  } else {
    return this.messages.partiallyCorrectAnswer;
  }
};
BaseQuestion.prototype.onCheckAnswer = function() {
  var grade = this.grade();
  this.displayFeedback(
      $('<div/>')
          .append($("<p/>").text(this.getMessageAboutScore(grade.score)))
          .append(grade.feedback));

  if (this.componentAudit) {
    var auditDict = {
      'instanceid': this.id,
      'answer': grade.answer,
      'score': grade.score,
      'type': this.type
    }
    if (this instanceof QuestionGroup) {
      auditDict['individualScores'] = grade.individualScores;
      auditDict['containedTypes'] = this.containedTypes;
    }
    this.componentAudit(auditDict);
  }
};
BaseQuestion.prototype.displayFeedback = function(feedback) {
  this.el.find('div.qt-feedback')
      .empty()
      .append(feedback)
      .removeClass('qt-hidden');
};
BaseQuestion.prototype.getWeight = function() {
  var weight = Number(this.data.weight);
  return (this.data.weight == null || isNaN(weight)) ? 1.0 : weight;
};

/**
 * A class to handle multiple choice questions.
 */
function McQuestion(el, questionData, messages, componentAudit) {
  BaseQuestion.call(this, el, questionData, messages, componentAudit);
  this.type = QUESTION_TYPES.MC_QUESTION;
}
BaseQuestion.bindSubclass(McQuestion);
McQuestion.prototype.bind = function() {
  var that = this;
  if (this.scored) {
    this.el.find('> div.qt-check-answer').addClass('qt-hidden');
    return this;
  }
  this.el.find('div.qt-check-answer > button.qt-check-answer-button')
      .click(function() {
        that.onCheckAnswer();
      });
    return this;
  };
McQuestion.prototype.grade = function() {
  var that = this;
  var answer = [];
  var score = 0.0;
  var feedback = $('<ul/>');
  this.el.find('div.qt-choices > div > input').each(function(i, input) {
    if (input.checked) {
      answer.push(i);
      score += parseFloat(that.data.choices[i].score);
      if (that.data.choices[i].feedback) {
        feedback.append($('<li/>').html(that.data.choices[i].feedback));
      }
    }
  });
  score = Math.round(Math.min(Math.max(score, 0), 1) * 100) / 100;
  return {
    answer: answer,
    score: score,
    feedback: feedback,
    type: this.type
  };
};
McQuestion.prototype.getStudentAnswer = function() {
  var state = [];
  this.el.find('div.qt-choices > div > input').each(function(i, input) {
    state[i] = input.checked;
  });
  return state;
};
McQuestion.prototype.setStudentAnswer = function(state) {
  if (state) {
    this.el.find('div.qt-choices > div > input').each(function(i, input) {
      if (typeof state[i] == 'boolean') {
        input.checked = state[i];
      }
    });
  }
};
McQuestion.prototype.makeReadOnly = function() {
  this.el.find('div.qt-choices > div > input').prop('disabled', true);
};

/**
 * A class to handle short answer questions.
 */
function SaQuestion(el, questionData, messages, componentAudit) {
  BaseQuestion.call(this, el, questionData, messages, componentAudit);
  this.type = QUESTION_TYPES.SA_QUESTION;
}
BaseQuestion.bindSubclass(SaQuestion);
SaQuestion.MATCHERS = {
  case_insensitive: {
    matches: function(answer, response) {
      return answer.toLowerCase() == response.toLowerCase();
    }
  },
  regex: {
    matches: function(answer, response) {
      return SaQuestion.parseRegExp(answer).test(response);
    }
  },
  numeric: {
    matches: function(answer, response) {
      return parseFloat(answer) == parseFloat(response);
    }
  }
};
SaQuestion.parseRegExp = function(regexpString) {
  var matches = regexpString.match(/\/(.*)\/([gim]*)/);
  if (matches) {
    return new RegExp(matches[1], matches[2]);
  } else {
    return new RegExp(regexpString);
  }
};
SaQuestion.prototype.bindHintButton = function() {
  var that = this;
  this.el.find('div.qt-hint > button.qt-hint-button')
      .click(function() {
        that.onShowHint();
      });
  return this;
};
SaQuestion.prototype.bind = function() {
  var that = this;
  if (this.scored) {
    this.el.find('> div.qt-check-answer').addClass('qt-hidden');
  } else {
    this.el.find('div.qt-check-answer > button.qt-check-answer-button')
        .click(function() {
          that.onCheckAnswer();
        });
  }
  this.bindHintButton();
  return this;
};
SaQuestion.prototype.onShowHint = function() {
  this.el.find('div.qt-feedback')
      .empty()
      .append($('<div/>').html(this.data.hint))
      .removeClass('qt-hidden');
};
SaQuestion.prototype.grade = function() {
  var response = this.el.find(
      'div.qt-response > input, div.qt-response > textarea').val();
  for (var i = 0; i < this.data.graders.length; i++) {
    var grader = this.data.graders[i];
    if (SaQuestion.MATCHERS[grader.matcher].matches(
        grader.response, response)) {
      var score = Math.min(Math.max(parseFloat(grader.score), 0), 1);
      return {
        answer: response,
        score: score,
        feedback: $('<div/>').html(grader.feedback),
        type: this.type
      };
    }
  }
  return {
    answer: response,
    score: 0.0,
    feedback: this.data.defaultFeedback,
    type: this.type
  };
};
SaQuestion.prototype.getStudentAnswer = function() {
  return {'response': this.el.find(
      'div.qt-response > input, div.qt-response > textarea').val()};
};
SaQuestion.prototype.setStudentAnswer = function(state) {
  if (state && state.response != undefined) {
    this.el.find('div.qt-response > input, div.qt-response > textarea')
        .val(state.response);
  }
};
SaQuestion.prototype.makeReadOnly = function() {
  this.el.find('div.qt-response > input, div.qt-response > textarea')
      .attr('disabled', true);
};

/**
 * A class to handle groups of questions.
 *
 * @param el JQuery root node of the question group
 * @param questionData the global question data object
 */
function QuestionGroup(el, questionData, messages, componentAudit) {
  BaseQuestion.call(this, el, questionData, messages, componentAudit);
  this.type = QUESTION_TYPES.QUESTION_GROUP;
  this.questionData = questionData;
  this.questions = [];
  this.init();
}
BaseQuestion.bindSubclass(QuestionGroup);
QuestionGroup.prototype.init = function() {
  var that = this;
  this.el.find('div.qt-mc-question.qt-embedded, div.qt-sa-question.qt-embedded')
      .each(function(index, element) {
        var elt = $(element);
        if (elt.hasClass('qt-mc-question')) {
          that.questions.push(new McQuestion(elt, that.questionData, [], null));
        } else {
          that.questions.push(new SaQuestion(elt, that.questionData, [], null)
              .bindHintButton());
        }
      });
};
QuestionGroup.prototype.getWeight = function() {
  // The following ensures that the weight is always strictly positive, thus
  // preventing division-by-zero errors.
  return this.getTotalPoints() + 1e-12;
};
QuestionGroup.prototype.bind = function() {
  var that = this;
  if (this.scored) {
    this.el.find('> div.qt-check-answer').addClass('qt-hidden');
    return this;
  }
  this.el.find('div.qt-check-answer > button.qt-check-answer-button')
      .click(function() {
        that.onCheckAnswer();
      });
  return this;
};
QuestionGroup.prototype.displayFeedback = function(feedback) {
  var that = this;
  $.each(feedback, function(index, feedback) {
    that.questions[index].displayFeedback(feedback);
  });
};
QuestionGroup.prototype.getTotalPoints = function() {
  var that = this;
  var total = 0.0;
  $.each(this.questions, function(index, question) {
    total += parseFloat(that.data[question.id].weight);
  });
  return total;
};
QuestionGroup.prototype.onCheckAnswer = function() {
  var grade = this.grade();
  this.el.find('> div.qt-feedback')
      .empty()
      .append($('<p/>').text(this.getMessageAboutScore(grade.score)))
      .removeClass('qt-hidden');
  this.displayFeedback(grade.feedback);

  this.componentAudit({
    'instanceid': this.id,
    'answer': grade.answer,
    'score': grade.score,
    'individualScores': grade.individualScores,
    'containedTypes': grade.containedTypes,
    'type': this.type
  });
};
QuestionGroup.prototype.grade = function() {
  // This returns a score that is normalized to a total weight of 1.
  var that = this;
  var answer = [];
  var score = 0.0;
  var feedback = [];
  var individualScores = [];
  var containedTypes = [];
  $.each(this.questions, function(index, question) {
    var grade = question.grade();
    answer.push(grade.answer);
    containedTypes.push(question.type);
    individualScores.push(grade.score);
    score += that.data[question.id].weight * grade.score;
    feedback.push(grade.feedback);
  });

  var totalWeight = this.getWeight();
  return {
    answer: answer,
    score: Math.round(100 * score / totalWeight) / 100,
    feedback: feedback,
    individualScores: individualScores,
    containedTypes: containedTypes
  };
};

QuestionGroup.prototype.getStudentAnswer = function() {
  var state = {};
  $.each(this.questions, function(index, question) {
    state[question.id] = question.getStudentAnswer();
  });
  return state;
};
QuestionGroup.prototype.setStudentAnswer = function(state) {
  if (state) {
    $.each(this.questions, function(index, question) {
      question.setStudentAnswer(state[question.id]);
    });
  }
};
QuestionGroup.prototype.makeReadOnly = function(state) {
  $.each(this.questions, function(index, question) {
    question.makeReadOnly();
  });
};

function gradeScoredLesson(questions, messages) {
  var score = 0.0;
  var totalWeight = 0.0;
  var answers = {'version': '1.5'};
  var individualScores = {};
  var containedTypes = {};
  $.each(questions, function(idx, question) {
    var grade = question.grade();
    if (question instanceof QuestionGroup) {
      individualScores[question.id] = grade.individualScores;
      containedTypes[question.id] = grade.containedTypes;
    } else {
      individualScores[question.id] = grade.score;
      containedTypes[question.id] = question.type;
    }
    answers[question.id] = grade.answer;
    score += grade.score * question.getWeight();
    totalWeight += question.getWeight();
    question.displayFeedback(grade.feedback);
  });
  score = Math.round(100 * score)/100;
  $('div.qt-grade-report')
      .text(messages.yourScoreIs + score + '/' + totalWeight.toFixed(0))
      .removeClass('qt-hidden');

  gcbLessonAudit({
    'type': 'scored-lesson',
    'answers': answers,
    'individualScores': individualScores,
    'score': score,
    'containedTypes': containedTypes
  });
}

function gradeAssessment(questions, unitId, xsrfToken) {
  var score = 0.0;
  // The following prevents division-by-zero errors.
  var totalWeight = 1e-12;
  var answers = {
    'version': '1.5', 'individualScores': {},
    'containedTypes': {}, 'answers': {}
  };
  $.each(questions, function(idx, question) {
    var grade = question.grade();
    score += grade.score * question.getWeight();
    totalWeight += question.getWeight();
    answers[question.id] = question.getStudentAnswer();
    answers.answers[question.id] = grade.answer;
    if (question instanceof QuestionGroup) {
      answers.individualScores[question.id] = grade.individualScores;
      answers.containedTypes[question.id] = grade.containedTypes;
    } else {
      answers.individualScores[question.id] = grade.score;
      answers.containedTypes[question.id] = question.type;
    }
  });

  var percentScore = (score / totalWeight * 100.0).toFixed(2);
  submitForm('answer', {
    'assessment_type': unitId,
    'score': percentScore,
    'answers': JSON.stringify(answers),
    'xsrf_token': xsrfToken
  });
}

function submitReview(isDraft, questions, unitId, xsrfToken, key) {
  // Need to pass the answers TO JUST THESE REVIEW QUESTIONS!
  // Pass xsrf_token, key, unit_id, is_drfat

  var answers = {'version': '1.5'};
  $.each(questions, function(index, question) {
    if ($(question.el).parents('div.review-form').length > 0) {
      answers[question.id] = question.getStudentAnswer();
    }
  });
  submitForm('review', {
    'is_draft': isDraft,
    'unit_id': unitId,
    'answers': JSON.stringify(answers),
    'xsrf_token': xsrfToken,
    'key': key
  });
}

function submitForm(action, hiddenData) {
  var form = $('<form/>')
      .css('display', 'none')
      .attr('method', 'post')
      .attr('action', action);
  $.each(hiddenData, function(key, value) {
    form.append($('<input type="hidden">').attr('name', key).val(value));
  });
  $('body').append(form);
  form.submit();
}

function findGcbQuestions() {
  function gcbAssessmentTagAudit(data_dict) {
    gcbTagEventAudit(data_dict, 'assessment');
  }
  var messages = window.assessmentTagMessages;
  var gcbQuestions = [];
  $('div.qt-mc-question.qt-standalone').each(function(index, element) {
    gcbQuestions.push(new McQuestion(
      $(element), window.questionData, messages,
      gcbAssessmentTagAudit).bind());
  });
  $('div.qt-sa-question.qt-standalone').each(function(index, element) {
    gcbQuestions.push(new SaQuestion(
      $(element), window.questionData, messages,
      gcbAssessmentTagAudit).bind());
  });
  $('div.qt-question-group').each(function(index, element) {
    gcbQuestions.push(new QuestionGroup(
      $(element), window.questionData, messages,
      gcbAssessmentTagAudit).bind());
  });

  // restore previous answers to questions
  if (window.questionData.savedAnswers) {
    $.each(gcbQuestions, function(index, question) {
      question.setStudentAnswer(window.questionData.savedAnswers[question.id]);
    });
  }

  // Make read-only views read-only
  $.each(gcbQuestions, function(index, question) {
    if ($(question.el).parents('div.assessment-readonly').length > 0) {
      question.makeReadOnly();
    }
  });

  // Bind the page-level grading buttons
  if (window.questionData.scored && gcbQuestions.length > 0) {
    $('div.qt-grade-scored-lesson')
        .removeClass('qt-hidden')
        .children('button').click(function() {
          gradeScoredLesson(gcbQuestions, messages);
        });
    $('div.qt-grade-assessment')
        .removeClass('qt-hidden')
        .children('button').click(function() {
          gradeAssessment(gcbQuestions, questionData.unitId,
              questionData.xsrfToken);
        });
    $('button.qt-save-draft')
        .click(function() {
          submitReview(true, gcbQuestions, questionData.unitId,
              questionData.xsrfToken, questionData.reviewKey);
        });
    $('button.qt-submit-review')
        .click(function() {
          submitReview(false, gcbQuestions, questionData.unitId,
            questionData.xsrfToken, questionData.reviewKey);
        });
  }
  return gcbQuestions;
}
