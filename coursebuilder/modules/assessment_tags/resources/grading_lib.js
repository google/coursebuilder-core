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

/**
 * Base class for rendering questions.
 */
function BaseQuestion(el, questionData, messages) {
  this.el = el;
  this.id = this.el.attr('id');
  this.data = questionData[this.id];
  this.scored = questionData.scored;
  this.messages = messages;
}
BaseQuestion.bindSubclass = function(subclass) {
  var tmp = function () {};
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
function McQuestion(el, questionData, messages) {
  BaseQuestion.call(this, el, questionData, messages);
}
BaseQuestion.bindSubclass(McQuestion);
McQuestion.prototype.bind = function () {
  var that = this;
  if (this.scored) {
    this.el.find('> div.qt-check-answer').addClass('qt-hidden');
    return this;
  }
  this.el.find('div.qt-check-answer > button.qt-check-answer-button')
      .click(function () {
        that.onCheckAnswer();
      });
    return this;
  };
McQuestion.prototype.grade = function() {
  var that = this;
  var score = 0.0;
  var feedback = $('<ul/>');
  this.el.find('div.qt-choices > div > input').each(function(i, input) {
    if (input.checked) {
      score += parseFloat(that.data.choices[i].score);
      if (that.data.choices[i].feedback) {
        feedback.append($('<li/>').text(that.data.choices[i].feedback));
      }
    }
  });
  return {
    score: Math.round(Math.min(Math.max(score, 0), 1) * 100) / 100,
    feedback: feedback
  };
}

/**
 * A class to handle short answer questions.
 */
function SaQuestion(el, questionData, messages) {
  BaseQuestion.call(this, el, questionData, messages);
}
BaseQuestion.bindSubclass(SaQuestion);
SaQuestion.prototype.MATCHERS = {
  case_insensitive: {
    matches: function(answer, response) {
      return answer.toLowerCase() == response.toLowerCase();
    }
  },
  regex: {
    matches: function(answer, response) {
      return new RegExp(answer).test(response);
    }
  },
  numeric: {
    matches: function(answer, response) {
      return parseFloat(answer) == parseFloat(response);
    }
  }
};
SaQuestion.prototype.bind = function() {
  var that = this;
  if (this.scored) {
    this.el.find('> div.qt-check-answer').addClass('qt-hidden');
    return this;
  }
  this.el.find('div.qt-check-answer > button.qt-check-answer-button')
      .click(function () {
        that.onCheckAnswer();
      });
  this.el.find('div.qt-hint > button.qt-hint-button')
      .click(function () {
        that.onShowHint();
      });
  return this;
};
SaQuestion.prototype.onShowHint = function() {
  this.el.find('div.qt-feedback')
      .empty()
      .append($('<div/>').text(this.data.hint))
      .removeClass('qt-hidden');
};
SaQuestion.prototype.grade = function() {
  var response = this.el.find('div.qt-response > input').val();
  for (var i = 0; i < this.data.graders.length; i++) {
    var grader = this.data.graders[i];
    if (this.MATCHERS[grader.matcher].matches(grader.response, response)) {
      return {
        score: Math.min(Math.max(parseFloat(grader.score), 0), 1),
        feedback: $('<div/>').text(grader.feedback)
      };
    }
  }
  return {score: 0.0, feedback: this.data.defaultFeedback};
};

/**
 * A class to handle groups of questions.
 *
 * @param el JQuery root node of the question group
 * @param questionData the global question data object
 */
function QuestionGroup(el, questionData, messages) {
  BaseQuestion.call(this, el, questionData, messages);
  this.questionData = questionData;
  this.questions = [];
  this.init();
}
BaseQuestion.bindSubclass(QuestionGroup);
QuestionGroup.prototype.init = function() {
  var that = this;
  this.el.find('div.qt-mc-question.qt-embedded')
      .each(function(index, element) {
        that.questions.push(new McQuestion($(element), that.questionData));
      });
  this.el.find('div.qt-sa-question.qt-embedded')
      .each(function(index, element) {
        that.questions.push(new SaQuestion($(element), that.questionData));
      });
};
QuestionGroup.prototype.getWeight = function() {
  return 1.0;
};
QuestionGroup.prototype.bind = function () {
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
      .append($('<p/>').text(this.getMessageAboutScore(
          grade.score / this.getTotalPoints())))
      .removeClass('qt-hidden');
  this.displayFeedback(grade.feedback);
};
QuestionGroup.prototype.grade = function() {
  var that = this;
  var score = 0.0;
  var feedback = [];
  $.each(this.questions, function (index, question) {
    var grade = question.grade();
    score += that.data[question.id].weight * grade.score;
    feedback.push(grade.feedback);
  });
  return {score: score, feedback: feedback};
};

function gradeScoredLesson(questions) {
  var score = 0.0;
  $.each(questions, function(idx, question) {
    var grade = question.grade();
    score += grade.score * question.getWeight();
    question.displayFeedback(grade.feedback);
  });
  $('div.qt-grade-report')
      .text(this.messages.yourScoreIs + score)
      .removeClass('qt-hidden');
}

function findGcbQuestions() {
  // TODO(jorr): Internationalize these messages
  var messages = {
    correctAnswer: 'Yes, the answer is correct.',
    incorrectAnswer: 'No, the answer is incorrect.',
    partiallyCorrectAnswer: 'The answer is partially correct.',
    yourScoreIs: 'Your score is: '
  };
  var gcbQuestions = [];
  $('div.qt-mc-question.qt-standalone').each(function(index, element) {
    gcbQuestions.push(new McQuestion($(element), window.questionData, messages)
        .bind());
  });
  $('div.qt-sa-question.qt-standalone').each(function(index, element) {
    gcbQuestions.push(new SaQuestion($(element), window.questionData, messages)
        .bind());
  });
  $('div.qt-question-group').each(function(index, element) {
    gcbQuestions.push(
        new QuestionGroup($(element), window.questionData, messages).bind());
  });
  if (window.questionData.scored && gcbQuestions.length > 0) {
    $('div.qt-grade-scored-lesson')
        .removeClass('qt-hidden')
        .click(function() {
          gradeScoredLesson(gcbQuestions);
        });
  }
  return gcbQuestions;
}
