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

_CORRECT_ANSWER_CUTOFF = 0.99;
_PARTIALLY_CORRECT_ANSWER_CUTOFF = 0.01;

function roundToTwoDecimalPlaces(x) {
  return Math.round(x * 100) / 100;
}

/**
 * Base class for rendering questions.
 */
function BaseQuestion(el, questionData, messages, componentAudit, scored) {
  this.el = el;
  this.id = this.el.attr('id');
  this.data = questionData[this.id];
  this.scored = scored;
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
  var p = $('<p></p>');
  if (score > _CORRECT_ANSWER_CUTOFF) {
    p.addClass('correct').text(this.messages.correctAnswer);
  } else if (score < _PARTIALLY_CORRECT_ANSWER_CUTOFF) {
    p.addClass('incorrect').text(this.messages.incorrectAnswer);
  } else {
    p.addClass('partially-correct').text(this.messages.partiallyCorrectAnswer);
  }
  return p;
};
BaseQuestion.prototype.onCheckAnswer = function() {
  var grade = this.grade();
  this.displayFeedback(
      $('<div/>')
          .append(this.getMessageAboutScore(grade.score))
          .append(grade.feedback));

  if (this.componentAudit) {
    var auditDict = {
      'instanceid': this.id,
      'quid': this.data.quid,
      'answer': grade.answer,
      'score': roundToTwoDecimalPlaces(grade.score),
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

function getIdentityPermutation(size) {
  var identity = [];
  for (var i = 0; i < size; i++) {
    identity[i] = i;
  }
  return identity;
}

function getRandomPermutation(size, random) {
  var source = getIdentityPermutation(size);
  var target = [];
  while (source.length) {
    var i = random() * source.length;
    target.push(source.splice(i, 1)[0]);
  }
  return target;
}

/**
 * A class to handle multiple choice questions.
 */
function McQuestion(el, questionData, messages, componentAudit, scored,
      random) {
  BaseQuestion.call(this, el, questionData, messages, componentAudit, scored);
  this.type = QUESTION_TYPES.MC_QUESTION;
  this.random = random || Math.random;
  this.choicesDivs = this.el.find('div.qt-choices > div');
  if (this.data.permuteChoices) {
    this.permutation = this._randomPermutation();
    this._applyPermutation(this.permutation);
  }
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
McQuestion.prototype._applyPermutation = function(perm) {
  var newChoices = [];
  for (var i = 0; i < perm.length; i++) {
    newChoices[perm[i]] = this.choicesDivs.eq(i);
  }
  this.el.find('div.qt-choices').empty().append(newChoices);
};
McQuestion.prototype._unapplyPermutation = function(perm) {
  var newChoices = [];
  for (var i = 0; i < perm.length; i++) {
    newChoices[i] = this.choicesDivs.eq(perm[i]);
  }
  this.el.find('div.qt-choices').empty().append(newChoices);
};
McQuestion.prototype._identityPermutation = function() {
  return getIdentityPermutation(this.choicesDivs.length);
};
McQuestion.prototype._randomPermutation = function() {
  return getRandomPermutation(this.choicesDivs.length, this.random);
};
McQuestion.prototype.grade = function() {
  var that = this;
  var answer = [];
  var score = 0.0;
  var feedbackDiv = $('<div>');
  var feedback = [];
  this.choicesDivs.find('> input').each(function() {
    var input = this;
    var index = $(input).data('index');
    if (input.checked) {
      answer.push(index);
      score += parseFloat(that.data.choices[index].score);
      if (that.data.choices[index].feedback) {
        feedback.push($('<li/>').html(that.data.choices[index].feedback));
      }
    }
  });
  score = roundToTwoDecimalPlaces(Math.min(Math.max(score, 0), 1));
  if (this.data.allOrNothingGrading) {
    score = score > _CORRECT_ANSWER_CUTOFF ? 1.0 : 0.0;
  }

  if (this.data.showAnswerWhenIncorrect) {
    var header = $('<h3 class="feedback-header">');

    var headerClass, headerText;
    if (score > _CORRECT_ANSWER_CUTOFF) {
      headerClass = 'correct';
      headerText = this.messages.correct;
    } else if (score < _PARTIALLY_CORRECT_ANSWER_CUTOFF) {
      headerClass = 'incorrect';
      headerText = this.messages.incorrect;
    } else {
      headerClass = 'partially-correct';
      headerText = this.messages.partiallyCorrect;
    }
    header.append($('<span>').addClass(headerClass).text(headerText));
    feedbackDiv.append(header);

    if (score <= _CORRECT_ANSWER_CUTOFF) {
      header.append($('<span>').addClass('correct-answer-heading')
          .text(this.messages.correctAnswerHeading));
      var correctChoicesUl = $('<ul class="correct-choices"></ul>');
      for (var i = 0; i < this.data.choices.length; i++) {
        var index = this.permutation ? this.permutation[i] : i;
        var choice = this.data.choices[index];
        if (choice.score > 0) {
          correctChoicesUl.append($('<li>').html(choice.text));
        }
      }
      feedbackDiv.append(correctChoicesUl);
    }
  }

  if (feedback.length) {
    feedbackDiv
          .append($('<h3 class="feedback-header">')
              .text(this.messages.targetedFeedbackHeading))
          .append($('<ul>').append(feedback));
  }
  if (this.data.defaultFeedback) {
    feedbackDiv
          .append($('<h3 class="feedback-header">')
              .text(this.messages.feedbackHeading))
          .append($('<div>').append(this.data.defaultFeedback));
  }

  return {
    answer: answer,
    score: score,
    feedback: feedbackDiv,
    type: this.type
  };
};
McQuestion.prototype.getStudentAnswer = function() {
  var responses = [];
  this.choicesDivs.find('> input').each(function() {
    var index = $(this).data('index');
    responses[index] = this.checked;
  });
  if (this.data.permuteChoices) {
    return {
      responses: responses,
      permutation: this.permutation
    };
  } else {
    return responses;
  }
};
McQuestion.prototype.setStudentAnswer = function(answer) {
  if (! answer) {
    return;
  }

  var responses, permutation;

  if (answer instanceof Array) {
    if (this.data.permuteChoices) {
      // The question was changed to permuted after the answer was submitted,
      // so upgrade the response to a permuted style, but with identity
      // permutation.
      responses = answer;
      permutation = this._identityPermutation();
    } else {
      responses = answer;
      permutation = null;
    }
  } else {
    if (! this.data.permuteChoices) {
      // If the answer was submitted while permuteChoices was set then display
      // it in that mode, coercing the question back to that mode if necessary,
      // so that the students sees the question as they answered it.
      this.data.permuteChoices = true;
      this.permutation = this._identityPermutation();
    }
    responses = answer.responses;
    permutation = answer.permutation;
  }

  this.choicesDivs.find('> input').each(function() {
    var index = $(this).data('index');
    if (typeof responses[index] == 'boolean') {
      this.checked = responses[index];
    }
  });

  if (this.data.permuteChoices) {
    this._unapplyPermutation(this.permutation);
    this._applyPermutation(permutation);
    this.permutation = permutation;
  }
};
McQuestion.prototype.makeReadOnly = function() {
  this.choicesDivs.find('> input').prop('disabled', true);
};

/**
 * A class to handle short answer questions.
 */
function SaQuestion(el, questionData, messages, componentAudit, scored) {
  BaseQuestion.call(this, el, questionData, messages, componentAudit, scored);
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
function QuestionGroup(el, questionData, messages, componentAudit, scored) {
  BaseQuestion.call(this, el, questionData, messages, componentAudit, scored);
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
          that.questions.push(new McQuestion(elt, that.questionData,
              that.messages, null, this.scored));
        } else {
          that.questions.push(new SaQuestion(elt, that.questionData,
              that.messages, null, this.scored).bindHintButton());
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
      .append(this.getMessageAboutScore(grade.score))
      .removeClass('qt-hidden');
  this.displayFeedback(grade.feedback);

  this.componentAudit({
    'instanceid': this.id,
    'answer': grade.answer,
    'score': roundToTwoDecimalPlaces(grade.score),
    'individualScores': grade.individualScores,
    'containedTypes': grade.containedTypes,
    'quids': grade.quids,
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
  var quids = [];
  $.each(this.questions, function(index, question) {
    var grade = question.grade();
    answer.push(grade.answer);
    containedTypes.push(question.type);
    individualScores.push(grade.score);
    quids.push(question.data.quid);
    score += that.data[question.id].weight * grade.score;
    feedback.push(grade.feedback);
  });

  var totalWeight = this.getWeight();
  return {
    answer: answer,
    score: score / totalWeight,
    feedback: feedback,
    individualScores: individualScores,
    containedTypes: containedTypes,
    quids: quids
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

function gradeScoredLesson(questions, messages, question_batch_id) {
  var score = 0.0;
  var totalWeight = 0.0;
  var answers = {'version': '1.5'};
  var individualScores = {};
  var containedTypes = {};
  var quids = {};
  $.each(questions, function(idx, question) {
    var grade = question.grade();
    if (question instanceof QuestionGroup) {
      individualScores[question.id] = grade.individualScores;
      containedTypes[question.id] = grade.containedTypes;
      quids[question.id] = grade.quids;
    } else {
      individualScores[question.id] = grade.score;
      containedTypes[question.id] = question.type;
      quids[question.id] = question.data.quid;
    }
    answers[question.id] = grade.answer;
    score += grade.score * question.getWeight();
    totalWeight += question.getWeight();
    question.displayFeedback(grade.feedback);
  });
  score = roundToTwoDecimalPlaces(score);
  $('div.qt-grade-report[data-question-batch-id="' + question_batch_id + '"]')
      .text(messages.yourScoreIs + score + '/' + totalWeight.toFixed(0))
      .removeClass('qt-hidden');

  gcbLessonAudit({
    'type': 'scored-lesson',
    'answers': answers,
    'individualScores': individualScores,
    'score': score,
    'containedTypes': containedTypes,
    'quids': quids
  });
}

function gradeAssessment(questions, unitId, xsrfToken, graderUri) {
  var score = 0.0;
  // The following prevents division-by-zero errors.
  var totalWeight = 1e-12;
  var answers = {
    'version': '1.5',
    'individualScores': {},
    'containedTypes': {},
    'answers': {},
    'quids': {},
    'rawScore': 0,
    'totalWeight': 0,
    'percentScore': 0.0
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
      answers.quids[question.id] = grade.quids;
    } else {
      answers.individualScores[question.id] = grade.score;
      answers.containedTypes[question.id] = question.type;
      answers.quids[question.id] = question.data.quid;
    }
  });

  var percentScore = score / totalWeight * 100.0;
  answers.rawScore = roundToTwoDecimalPlaces(score);
  answers.totalWeight = roundToTwoDecimalPlaces(totalWeight);
  answers.percentScore = roundToTwoDecimalPlaces(percentScore);

  submitForm(graderUri || 'answer', {
    'assessment_type': unitId,
    'score': percentScore.toFixed(2),
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

/**
    * This will move the submit answers button to a div with class
    * 'qt-assessment-button-bar-location' if the lesson author has included
    * exactly one.
    */
function maybeMoveGradingButton() {
  var buttonBarDiv = $('div.qt-assessment-button-bar');
  var buttonBarPreferredLocation = $('div.qt-assessment-button-bar-location');
  if (buttonBarDiv.length == 1 && buttonBarPreferredLocation.length == 1) {
    buttonBarDiv.appendTo(buttonBarPreferredLocation);
  }
}

function getQuestionBatchId(element) {
  var parents = $(element).parents('[data-question-batch-id]')
  if (parents.length > 0) {
    return $(parents[0]).data('question-batch-id');
  } else {
    return 'unowned';
  }
}

function findGcbQuestions() {
  function gcbAssessmentTagAudit(data_dict) {
    gcbTagEventAudit(data_dict, 'assessment');
  }
  var messages = window.assessmentTagMessages;
  var gcbQuestions = {};

  function addQuestion(gcbQuestions, element, constructor) {
    var parent = $(element).parents('[data-question-batch-id]')[0];
    var scored = ($(parent).data('scored').toLowerCase() == 'true');
    var questionBatchId = $(parent).data('question-batch-id');
    if (!(questionBatchId in gcbQuestions)) {
      gcbQuestions[questionBatchId] = [];
    }
    gcbQuestions[questionBatchId].push(
        new constructor($(element), window.questionData, messages,
            gcbAssessmentTagAudit, scored).bind());
  }
  $('div.qt-mc-question.qt-standalone').each(function(index, element) {
    addQuestion(gcbQuestions, element, McQuestion);
  });
  $('div.qt-sa-question.qt-standalone').each(function(index, element) {
    addQuestion(gcbQuestions, element, SaQuestion);
  });
  $('div.qt-question-group').each(function(index, element) {
    addQuestion(gcbQuestions, element, QuestionGroup);
  });

  if (window.questionData.savedAnswers) {
    for (var group in gcbQuestions) {
      $.each(gcbQuestions[group], function(index, question) {

        // restore previous answers to questions
        question.setStudentAnswer(
            window.questionData.savedAnswers[question.id]);

        // Make read-only views read-only
        if ($(question.el).parents('div.assessment-readonly').length > 0) {
          question.makeReadOnly();
        }

        // Display feedback
        if ($(question.el).parents('div.show-feedback').length > 0) {
          var grade = question.grade();
          question.displayFeedback(grade.feedback);
        }
      });
    }
  }

  // Bind the page-level grading buttons
  if (! $.isEmptyObject(gcbQuestions)) {
    $('div.qt-grade-scored-lesson')
        .css('display', '')
        .children('button').click(function(event) {
          var dataDiv = $(
              $(event.target).parents('[data-question-batch-id]')[0]);
          var questionBatchId = dataDiv.data('question-batch-id');
          gradeScoredLesson(gcbQuestions[questionBatchId],
              messages, questionBatchId);
        });
    $('div.qt-grade-assessment')
        .css('display', '')
        .children('button').click(function(event) {
          var dataDiv = $(
              $(event.target).parents('[data-question-batch-id]')[0]);
          var questionBatchId = dataDiv.data('question-batch-id');
          var unitId = dataDiv.data('unit-id');
          var xsrfToken = dataDiv.data('xsrf-token');
          var graderUri = dataDiv.data('grader-uri');
          gradeAssessment(gcbQuestions[questionBatchId], unitId, xsrfToken,
              graderUri);
        });
    $('button.qt-save-draft')
        .click(function(event) {
          var dataDiv = $(
              $(event.target).parents('[data-question-batch-id]')[0]);
          var questionBatchId = dataDiv.data('question-batch-id');
          var unitId = dataDiv.data('unit-id');
          var xsrfToken = dataDiv.data('xsrf-token');
          var reviewKey = dataDiv.data('review-key');
          submitReview(true, gcbQuestions[questionBatchId], unitId,
                       xsrfToken, reviewKey);
        });
    $('button.qt-submit-review')
        .click(function(event) {
          var dataDiv = $(
              $(event.target).parents('[data-question-batch-id]')[0]);
          var questionBatchId = dataDiv.data('question-batch-id');
          var unitId = dataDiv.data('unit-id');
          var xsrfToken = dataDiv.data('xsrf-token');
          var reviewKey = dataDiv.data('review-key');
          submitReview(false, gcbQuestions[questionBatchId], unitId,
                       xsrfToken, reviewKey);
        });
  }

  maybeMoveGradingButton();

  return gcbQuestions;
}
