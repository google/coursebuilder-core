/**
 * A class to handle multiple choice questions.
 */
function McQuestion(el, questionData) {
  this.el = el;
  this.data = questionData[this.el.attr('id')];
}
McQuestion.prototype = {
  bind: function () {
    var that = this;
    this.el.find('div.qt-check-answer > button.qt-check-answer-button')
        .click(function () {
          that.onCheckAnswer();
        });
    return this;
  },
  onCheckAnswer: function() {
    var grade = this.grade();
    this.el.find('div.qt-feedback').empty()
        .append($('<div class="qt-score"/>')
            .text('Your score is: ' + grade.score))
        .append(grade.feedback)
        .removeClass('qt-hidden');
  },
  grade: function() {
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
};

/**
 * A class to handle short answer questions.
 */
function SaQuestion(el, questionData) {
  this.el = el;
  this.data = questionData[this.el.attr('id')];
}
SaQuestion.prototype = {
  MATCHERS: {
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
  },
  bind: function() {
    var that = this;
    this.el.find('div.qt-check-answer > button.qt-check-answer-button')
        .click(function () {
          that.onCheckAnswer();
        });
    this.el
        .find('div.qt-check-answer > button.qt-skip-and-show-answer-button')
        .click(function () {
          that.onSkipAndShowAnswer();
        });
    return this;
  },
  onCheckAnswer: function() {
    var grade = this.grade();
    this.el.find('div.qt-feedback')
        .empty()
        .append($('<div class="qt-score"/>')
              .text('Your score is: ' + grade.score))
        .append(grade.feedback)
        .removeClass('qt-hidden');
  },
  onSkipAndShowAnswer: function() {
    this.el.find('div.qt-feedback')
        .empty()
        .append($('<div/>').text(this.data.hint))
        .removeClass('qt-hidden');
  },
  grade: function() {
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
    return {score: 0.0, feedback: this.data.incorrectFeedback};
  }
};

function findGcbQuestions() {
  var gcbQuestions = [];
  $('div.qt-mc-question').each(function(index, element) {
    gcbQuestions.push(new McQuestion($(element), window.questionData).bind());
  });
  $('div.qt-sa-question').each(function(index, element) {
    gcbQuestions.push(new SaQuestion($(element), window.questionData).bind());
  });
  return gcbQuestions;
}
