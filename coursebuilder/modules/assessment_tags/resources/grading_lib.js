/**
 * Base class for rendering questions.
 */
function BaseQuestion() {}
BaseQuestion.prototype.onCheckAnswer = function() {
  var grade = this.grade();
  this.displayScoreAndFeedback(grade.score, grade.feedback);
};
BaseQuestion.prototype.displayScoreAndFeedback = function(score, feedback) {
  this.el.find('div.qt-feedback').empty()
      .append($('<div class="qt-score"/>')
          .text('Your score is: ' + score))
      .append(feedback)
      .removeClass('qt-hidden');
};
BaseQuestion.prototype.displayFeedback = function(feedback) {
  this.el.find('div.qt-feedback')
      .empty().append(feedback).removeClass('qt-hidden');
};

/**
 * A class to handle multiple choice questions.
 */
function McQuestion(el, questionData) {
  this.el = el;
  this.id = this.el.attr('id');
  this.data = questionData[this.id];
}
McQuestion.prototype = new BaseQuestion();
McQuestion.prototype.bind = function () {
  var that = this;
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
      score += parseFloat(that.data[i].score);
      if (that.data[i].feedback) {
        feedback.append($('<li/>').text(that.data[i].feedback));
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
function SaQuestion(el, questionData) {
  this.el = el;
  this.id = this.el.attr('id');
  this.data = questionData[this.id];
}
SaQuestion.prototype = new BaseQuestion();
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
function QuestionGroup(el, questionData) {
  this.el = el;
  this.questionData = questionData;
  this.data = this.questionData[this.el.attr('id')];
  this.questions = [];
  this.init();
}
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
QuestionGroup.prototype.bind = function () {
  var that = this;
  this.el.find('div.qt-check-answer > button.qt-check-answer-button')
      .click(function() {
        that.onCheckAnswer();
      });
  return this;
};
QuestionGroup.prototype.onCheckAnswer = function() {
  var that = this;
  var grade = this.grade();

  this.el.find('> div.qt-feedback').empty()
      .append($('<div class="qt-score"/>')
          .text('Your score is: ' + grade.score))
      .removeClass('qt-hidden');

  $.each(grade.feedback, function(index, feedback) {
    that.questions[index].displayFeedback(feedback);
  });
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

function findGcbQuestions() {
  var gcbQuestions = [];
  $('div.qt-mc-question.qt-standalone').each(function(index, element) {
    gcbQuestions.push(new McQuestion($(element), window.questionData).bind());
  });
  $('div.qt-sa-question.qt-standalone').each(function(index, element) {
    gcbQuestions.push(new SaQuestion($(element), window.questionData).bind());
  });
  $('div.qt-question-group').each(function(index, element) {
    gcbQuestions.push(new QuestionGroup($(element), window.questionData)
        .bind());
  });
  return gcbQuestions;
}
