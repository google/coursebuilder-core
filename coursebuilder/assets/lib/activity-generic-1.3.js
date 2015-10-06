// Copyright 2013 Google Inc. All Rights Reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS-IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Shared generic code for activities and assessments
// requires jQuery (>= 1.7.2)

// Original activity and assessment code written by Maggie Johnson
// Refactored version by Philip Guo

// time on page
var gcbBeginningOfTime = new Date();

// highlight the correct answer
var highlightColor = '#3BB9FF';

var globallyUniqueTag = 0; // each question should have a unique tag

function getFreshTag() {
  globallyUniqueTag++;
  return globallyUniqueTag;
}

// controls sending events to the server; off by default; override to enable
var gcbCanRecordStudentEvents = false;

// various XSRF tokens
var eventXsrfToken = '';
var assessmentXsrfToken = '';

function gcbTagEventAudit(data_dict, name) {
  gcbAudit(gcbCanRecordStudentEvents, data_dict, 'tag-' + name, true);
}

function gcbPageEventAudit(data_dict, name) {
  gcbAudit(gcbCanRecordStudentEvents, data_dict, name, false);
}

function gcbActivityAudit(data_dict) {
  gcbAudit(gcbCanRecordStudentEvents, data_dict, 'attempt-activity', true);
}

function gcbLessonAudit(data_dict) {
  gcbAudit(gcbCanRecordStudentEvents, data_dict, 'attempt-lesson', true);
}

function gcbAssessmentAudit(data_dict) {
  gcbAudit(gcbCanRecordStudentEvents, data_dict, 'attempt-assessment', true);
}

function gcbAudit(can_post, data_dict, source, is_async) {
  // There may be a course-specific config to save $$ by preventing us
  // from emitting too much volume to AppEngine; respect that setting.
  if (can_post) {
    data_dict['location'] = '' + window.location;
    data_dict['loc'] = {}
    data_dict['loc']['page_locale'] = $('body').data('gcb-page-locale')
    var request = {
        'source': source,
        'payload': JSON.stringify(data_dict),
        'xsrf_token': eventXsrfToken};
    $.ajax({
        url: 'rest/events',
        type: 'POST',
        async: is_async,
        data: {'request': JSON.stringify(request)},
        success: function(){},
        error: function(){}
    });
  }

  // ----------------------------------------------------------------------
  // Report to the Google Tag manager, if it's configured.  The 'dataLayer'
  // object is hooked to override the normal array's 'push()' with a handler.
  // This is the only place in CB that will emit 'event' as a name into the
  // dataLayer.  Thus, this should be the only place that causes a well-
  // behaved set of tag rules to actually do anything.  Note that we get
  // here both on page load (from $(document).ready(), below), as well as
  // from the various on-page events.
  if ('dataLayer' in window) {

    // Translate event names to be a bit more regularized.  This permits
    // simpler rules in the tag manager (e.g., "{{event}} startswith
    // 'gcb.page-'" means it's a page-level event.  Being able to make this
    // distinction is convenient for passing along facts to Google Analytics.
    switch (source) {
    case 'enter-page':
    case 'exit-page':
      source = 'page.' + source
      break;
    default:
      source = 'event.' + source
      break;
    }

    // Always prefix our events so that clients can distinguish between our
    // events (starting with 'gcb.'), Google Tag Manager events (start with
    // 'gtm.'), and any events from their own content or other libraries they
    // might be pulling in.
    source = 'gcb.' + source

    var tmp = {}
    $.extend(tmp, data_dict, {'event': source, 'is_async': is_async});
    dataLayer.push(tmp);
  }
}

// Returns the value of a URL parameter, if it exists.
function getParamFromUrlByName(name) {
  return decodeURI(
      (RegExp(name + '=' + '(.+?)(&|$)').exec(location.search)||[,null])[1]
  );
}

// 'choices' is a list of choices, where each element is:
//    [choice label, is correct? (boolean), output when this choice is submitted]
// 'domRoot' is the dom element to append HTML onto
// 'index' is the index of this activity in the containing list
function generateMultipleChoiceQuestion(params, domRoot, index) {
  var choices = params.choices;
  var tag = getFreshTag();
  var radioButtonGroupName = 'q' + tag;

  if ("questionHTML" in params) {
    domRoot.append(params.questionHTML);
  }

  // create radio buttons
  $.each(choices, function(i, elt) {
    var label = elt[0];
    var isCorrect = elt[1];
    var buttonId = radioButtonGroupName + '-' + i;
    if (isCorrect) {
      domRoot.append(
          '<span class="correct_' + tag + '">' +
          '<input type="radio" name="' + radioButtonGroupName + '" ' +
          'id="' + buttonId + '" value="correct"> ' +
          '<label for="' + buttonId + '">' + label + '</label></span>');
    }
    else {
      domRoot.append('<input type="radio" name="' + radioButtonGroupName + '" ' +
          'id="' + buttonId + '"> ' +
          '<label for="' + buttonId + '">' + label + '</label>');
    }
    domRoot.append('<br>');
  });

  domRoot.append('<br>');
  domRoot.append('<p/><button class="gcb-button" ' +
      'id="submit_' + tag + '">' + trans.CHECK_ANSWER_TEXT + '</button>');
  domRoot.append(
      '<p/><textarea style="width: 600px; height: 50px;" readonly="true" ' +
      'id="output_' + tag + '"></textarea>');


  var choiceInputs = $('input[name=' + radioButtonGroupName + ']');

  // clear output and highlighting whenever a checkbox is clicked
  choiceInputs.click(function() {
    $('.correct_' + tag).css('background-color', '');
    $('#output_' + tag).val('');
  });


  // treat enter keypresses in the same way as clicks
  $('#submit_' + tag).keydown(function(e) {
    if (e.keyCode === 13) {
      $(this).trigger('click', true);
      e.preventDefault();
    }
  });

  // check inputs and update output
  $('#submit_' + tag).click(function() {
    var answerChosen = false;
    for (var i = 0; i < choiceInputs.length; i++) {
      var isCorrect = choices[i][1];
      var outputMsg = choices[i][2];

      var isChecked = choiceInputs[i].checked;
      if (isChecked) {
        gcbActivityAudit({
            'index': index, 'type': 'activity-choice', 'value': i,
            'correct': isCorrect});
        $('#output_' + tag).val(outputMsg);
        $('#output_' + tag).focus();
        if (isCorrect) {
          $('.correct_' + tag).css('background-color', highlightColor);
        }
        answerChosen = true;
      }
    }

    if (!answerChosen) {
      $('#output_' + tag).val(trans.SELECT_ANSWER_PROMPT);
      $('#output_' + tag).focus();
    }
  });
}

// Generate a collection of multiple choice questions
// 'params' is an object containing parameters
// 'domRoot' is the dom element to append HTML onto
// 'index' is the index of this activity in the containing list
function generateMultipleChoiceGroupQuestion(params, domRoot, index) {

  // 'questionsList' is an ordered list of questions, where each element is:
  //     {questionHTML: <HTML of question>,
  //      choices: <list of choice labels>,
  //      correctIndex: <index of correct choice>}
  // 'allCorrectOutput' is what to display when ALL of the answers are correct
  // 'someIncorrectOutput' is what to display when not all of the answers are correct
  var questionsList = params.questionsList;
  var allCorrectOutput = params.allCorrectOutput;
  var someIncorrectOutput = params.someIncorrectOutput;
  var used_tags = [];

  if ("questionGroupHTML" in params) {
    domRoot.append(params.questionGroupHTML);
  }

  var allCorrectMinCount = questionsList.length;
  if ("allCorrectMinCount" in params) {
    var count = params.allCorrectMinCount;
    if (count >= 0 && count <= questionsList.length) {
      allCorrectMinCount = count;
    }
  }

  // helper function to determine the count of correct answers for a question
  var correctAnswerCount = function(q) {
    if (q.correctIndex instanceof Array) {
      var count = q.correctIndex.length;
      if (("multiSelect" in q) && !q.multiSelect) {
        return 1;
      }
      return count;
    } else {
      return 1;
    }
  };

  // helper function to determine if item represents a correct answer
  var isCorrectAnswer = function(q, index) {
    if (q.correctIndex instanceof Array) {
      return $.inArray(index, q.correctIndex) != -1;
    } else {
      return index == q.correctIndex;
    }
  };

  // create questions
  $.each(questionsList, function(i, q) {
    var tag = getFreshTag();
    used_tags.push(tag);

    var radioButtonGroupName = 'q' + tag;

    // choose item type: radio button or checkbox
    var itemType = 'radio';
    if ((q.correctIndex instanceof Array) && (q.correctIndex.length > 1)) {
      itemType = 'checkbox';
    }
    if (("multiSelect" in q) && !q.multiSelect) {
      itemType = 'radio';
    }

    // create question HTML
    domRoot.append(q.questionHTML);
    domRoot.append('<br>');

    // create radio buttons
    $.each(q.choices, function(j, choiceLabel) {
      var buttonId = radioButtonGroupName + '-' + i + '-' + j;
      if (isCorrectAnswer(q, j)) {
        domRoot.append(
            '<span class="correct_' + tag + '">' +
            '<input type="' + itemType + '" name="' + radioButtonGroupName + '" ' +
            'id="' + buttonId + '" value="correct"> ' +
            '<label for="' + buttonId + '">' + choiceLabel + '</label></span>');
      } else {
        domRoot.append(
            '<input type="' + itemType + '" name="' + radioButtonGroupName + '" ' +
            'id="' + buttonId + '"> ' +
            '<label for="' + buttonId + '">' + choiceLabel + '</label>');
      }
      domRoot.append('<br>');
    });

    domRoot.append('<p/>');
  });


  var toplevel_tag = getFreshTag();

  domRoot.append(
      '<p/><button class="gcb-button" id="submit_' +
      toplevel_tag + '">' + trans.CHECK_ANSWERS_TEXT + '</button>');
  domRoot.append(
      '<p/><textarea style="width: 600px; height: 100px;" readonly="true" ' +
      'id="output_' + toplevel_tag + '"></textarea>');


  // clear output and highlighting for ALL questions whenever any checkbox is clicked
  $.each(questionsList, function(ind, q) {
    var tag = used_tags[ind];
    var radioButtonGroupName = 'q' + tag;
    var choiceInputs = $('input[name=' + radioButtonGroupName + ']');

    choiceInputs.click(function() {
      $.each(used_tags, function(i, t) {
        $('.correct_' + t).css('background-color', '');
      });
      $('#output_' + toplevel_tag).val('');
    });
  });


  // treat enter keypresses in the same way as clicks
  $('#submit_' + toplevel_tag).keydown(function(e) {
    if (e.keyCode === 13) {
      $(this).trigger('click', true);
      e.preventDefault();
    }
  });

  // handle question submission
  $('#submit_' + toplevel_tag).click(function() {
    var numChecked = 0;  // # of questions where answer was given by the student
    var numCorrect = 0;  // # of questions where answer was correct
    answers = []

    $.each(questionsList, function(ind, q) {
      var tag = used_tags[ind];
      var radioButtonGroupName = 'q' + tag;
      var choiceInputs = $('input[name=' + radioButtonGroupName + ']');

      var numInputChecked = 0;  // # of <input>s that were given by the student
      var numInputCorrect = 0;  // # of <input>s that were correct
      var answerIndexes = [];  // indexes of the choices submitted by the student

      // check each <input> for correctness
      for (var i = 0; i < choiceInputs.length; i++) {
        var isChecked = choiceInputs[i].checked;
        var isCorrect = isCorrectAnswer(q, i);
        if (isChecked) {
          numInputChecked++;
          if (isCorrect) {
             numInputCorrect++;
          }
          answerIndexes.push(i);
        }
      }

      // decide if all inputs were correct and record the result
      var allInputsAreCorrect = false;
      if (
          numInputChecked == numInputCorrect &&
          numInputCorrect == correctAnswerCount(q)) {
        numCorrect++;
        allInputsAreCorrect = true;
      }
      answers.push({
          'index': ind,
          'value': answerIndexes, 'correct': allInputsAreCorrect});
    });

    gcbActivityAudit({
        'index': index, 'type': 'activity-group', 'values': answers,
        'num_expected': allCorrectMinCount,
        'num_submitted': numChecked, 'num_correct': numCorrect});

    if (numCorrect >= allCorrectMinCount) {
      var verdict = trans.ALL_CORRECT_TEXT;
      if (numCorrect < questionsList.length) {
        verdict =
            trans.NUM_CORRECT_TEXT + ': ' +
            numCorrect + '/' + questionsList.length + '. ';
      }
      $.each(used_tags, function(i, t) {
        $('.correct_' + t).css('background-color', highlightColor);
      });
      $('#output_' + toplevel_tag).val(verdict + ' ' + allCorrectOutput);
      $('#output_' + toplevel_tag).focus();
    } else {
      $('#output_' + toplevel_tag).val(
          trans.NUM_CORRECT_TEXT + ': ' + numCorrect + '/' + questionsList.length +
          '.\n\n' + someIncorrectOutput);
      $('#output_' + toplevel_tag).focus();
    }
  });
}

// 'params' is an object containing parameters (some optional)
// 'domRoot' is the dom element to append HTML onto
// 'index' is the index of this activity in the containing list
function generateFreetextQuestion(params, domRoot, index) {

  // 'correctAnswerRegex' is a regular expression that matches the correct answer
  // 'correctAnswerOutput' and 'incorrectAnswerOutput' are what to display
  // when the checked answer is correct or not. If those are both null,
  // then don't generate a 'Check Answer' button.
  // 'showAnswerOutput' is what to display when the user clicks the 'Skip &
  // Show Answer' button (if null, then don't display that option).
  var correctAnswerRegex = params.correctAnswerRegex;
  var correctAnswerOutput = params.correctAnswerOutput;
  var incorrectAnswerOutput = params.incorrectAnswerOutput;
  var showAnswerOutput = params.showAnswerOutput;
  var showAnswerPrompt = params.showAnswerPrompt || trans.SHOW_ANSWER_TEXT; // optional parameter
  var outputHeight = params.outputHeight || '50px'; // optional parameter
  var tag = getFreshTag();

  if ("questionHTML" in params) {
    domRoot.append(params.questionHTML);
  }

  domRoot.append(
      '&nbsp;&nbsp;<input type="text" style="width: 400px; ' +
      'class="alphanumericOnly" id="input_' + tag + '">');
  if (correctAnswerOutput && incorrectAnswerOutput) {
    domRoot.append('<p/><button class="gcb-button" ' +
        'id="submit_' + tag + '">' + trans.CHECK_ANSWER_TEXT + '</button>');
  }
  if (showAnswerOutput) {
    domRoot.append(
        '<p/><button class="gcb-button" ' +
        'id="skip_and_show_' + tag + '">' +
        showAnswerPrompt + '</button>');
  }
  domRoot.append(
      '<p/><textarea style="width: 600px; height: ' + outputHeight + ';" ' +
      'readonly="true" id="output_' + tag + '"></textarea>');


  // we need to wait until ALL elements are in the DOM before binding event handlers

  $('#input_' + tag).focus(function() {
    $('#output_' + tag).val('');
  });

  if (correctAnswerOutput && incorrectAnswerOutput) {
    // treat enter keypresses in the same way as clicks
    $('#submit_' + tag).keydown(function(e) {
      if (e.keyCode === 13) {
        $(this).trigger('click', true);
        e.preventDefault();
      }
    });

    $('#submit_' + tag).click(function() {
      var textValue = $('#input_' + tag).val();
      textValue = textValue.replace(/^\s+/,''); //trim leading spaces
      textValue = textValue.replace(/\s+$/,''); //trim trailing spaces

      var isCorrect = correctAnswerRegex.test(textValue);
      gcbActivityAudit({
          'index': index, 'type': 'activity-freetext', 'value': textValue,
          'correct': isCorrect})
      if (isCorrect) {
        $('#output_' + tag).val(correctAnswerOutput);
        $('#output_' + tag).focus();
      }
      else {
        $('#output_' + tag).val(incorrectAnswerOutput);
        $('#output_' + tag).focus();
      }
    });
  }

  if (showAnswerOutput) {
    $('#skip_and_show_' + tag).click(function() {
      var textValue = $('#input_' + tag).val();
      gcbActivityAudit({
          'index': index, 'type': 'activity-freetext', 'value': textValue,
          'correct': null})
      $('#output_' + tag).val(showAnswerOutput);
      $('#output_' + tag).focus();
    });
  }
}

// Takes a list of HTML element strings and special question objects and renders
// HTML onto domRoot
//
// The main caveat here is that each HTML string must be a FULLY-FORMED HTML
// element that can be appended wholesale to the DOM, not a partial element.
function renderActivity(contentsLst, domRoot) {
  $.each(contentsLst, function(i, e) {
    if (typeof e == 'string') {
      domRoot.append(e);
    } else {
      // dispatch on type:
      if (e.questionType == 'multiple choice') {
        generateMultipleChoiceQuestion(e, domRoot, i);
      }
      else if (e.questionType == 'multiple choice group') {
        generateMultipleChoiceGroupQuestion(e, domRoot, i);
      }
      else if (e.questionType == 'freetext') {
        generateFreetextQuestion(e, domRoot, i);
      }
      else {
        alert('Error in renderActivity: e.questionType is not in ' +
              '{\'multiple choice\', \'multiple choice group\', \'freetext\'}');
      }
    }
  });
}

// Takes a special 'assessment' object and renders it as HTML under domRoot
function renderAssessment(assessment, domRoot) {
  // first surround everything with a form
  domRoot.html('<form name="assessment"></form>');
  domRoot = domRoot.find('form');

  if (assessment.preamble) {
    domRoot.append(assessment.preamble);
  }

  var questionsOL = $('<ol></ol>');
  domRoot.append(questionsOL);

  $.each(assessment.questionsList, function(questionNum, q) {
    questionsOL.append('<li></li>');

    var curLI = questionsOL.find('li:last');
    curLI.append(q.questionHTML);
    curLI.append('<p/>');

    // The student's saved answer for this question, if it exists.
    var savedAnswer = null;
    if (assessmentGlobals.savedAnswers &&
        questionNum < assessmentGlobals.savedAnswers.length) {
      savedAnswer = assessmentGlobals.savedAnswers[questionNum];
    }

    // Dispatch to specialized handler depending on the existence of particular fields:
    //   choices              - multiple choice question (with exactly one correct answer)
    //   correctAnswerString  - case-insensitive substring match
    //   correctAnswerRegex   - freetext regular expression match
    //   correctAnswerNumeric - freetext numeric match
    if (q.choices) {
      $.each(q.choices, function(i, c) {
        var buttonId = 'q' + questionNum + '-' + i;

        var checkedAttr = '';
        if (savedAnswer !== null && i == savedAnswer) {
          checkedAttr = ' checked=true ';
        }

        if (typeof c == 'string') {
          // incorrect choice
          curLI.append('<input type="radio" name="q' + questionNum + '" id="' +
              buttonId + '" ' + checkedAttr + ' >&nbsp;<label for="' + buttonId +
              '">' + c + '</label><br>');
        } else {
          // wrapped in correct() ...
          if (c[0] != 'correct') {
            alert('Error: Malformed question.');
          }
          // correct choice
          curLI.append('<input type="radio" name="q' + questionNum + '" id="' +
              buttonId + '" ' + checkedAttr + ' value="correct">&nbsp;<label for="' +
              buttonId + '">' + c[1] + '</label><br>');
        }
      });
    } else if (q.correctAnswerString || q.correctAnswerRegex || q.correctAnswerNumeric) {
      if (('multiLine' in q) && q.multiLine) {
        curLI.append('Answer:<br>');

        var textarea = $('<textarea id="q' + questionNum + '" style="width: 100%" rows="7"></textarea>');
        if (savedAnswer != null) {
          textarea.text(savedAnswer);
        }
        curLI.append(textarea);

      } else {
        curLI.append('Answer:&nbsp;&nbsp;');

        var inputField = $('<input type="text" class="alphanumericOnly" ' +
            'style="border-style: solid; border-color: black; border-width: 1px;" ' +
            'id="q' + questionNum + '" size="50">');
        if (savedAnswer !== null) {
          inputField.val(savedAnswer);
        }
        curLI.append(inputField);
      }
    } else {
      alert('Error: Invalid question type.');
    }

    curLI.append('<br><br>');
  });

  if (assessmentGlobals.isReviewForm) {
    domRoot.append(
        '<br><button type="button" class="gcb-button" id="saveDraftBtn">' +
        trans.SAVE_DRAFT_TEXT + '</button>&nbsp;&nbsp;' +
        '<button type="button" class="gcb-button" id="submitAnswersBtn">' +
        trans.SUBMIT_REVIEW_TEXT + '</button>');
  } else {
    if (assessment.checkAnswers) {
      domRoot.append(
          '<button type="button" class="gcb-button" id="checkAnswersBtn">' +
          trans.CHECK_ANSWERS_TEXT + '</button><p/>');
      domRoot.append('<p/><textarea style="width: 600px; height: 120px;" ' +
          'readonly="true" id="answerOutput"></textarea>');
    }
    var buttonText = trans.SUBMIT_ANSWERS_TEXT;
    if (assessmentGlobals.grader == 'human') {
      buttonText = trans.SUBMIT_ASSIGNMENT_TEXT;
    }
    var disabledHtml = transientStudent ? ' disabled="true" ' : '';
    domRoot.append(
        '<br><button type="button" class="gcb-button" id="submitAnswersBtn" ' +
        disabledHtml + '>' + buttonText + '</button>');
  }

  function checkOrSubmitAnswers(submitAnswers) {
    $('#answerOutput').html('');

    var numCorrect = 0;
    var scoreArray = [];
    var lessonsToRead = [];
    var userInput = [];
    // The student's score.
    var totalScore = 0;
    // The maximum possible score.
    var totalWeight = 0;

    $.each(assessment.questionsList, function(questionNum, q) {
      // The score of the student for this question, independent of the
      // question's weight.
      var score = 0;
      var isCorrect = false;
      var weight = (q.weight || 1);
      totalWeight += weight;

      if (q.choices) {
        var userInputRecorded = false;
        var radioGroup = document.assessment['q' + questionNum];

        for (var i = 0; i < radioGroup.length; i++) {
          if (radioGroup[i].checked) {
            isCorrect = radioGroup[i].value == 'correct';

            // The length of the choiceScores array must be the same as the
            // length of the radioGroup, otherwise this is a badly-formatted
            // question and the choiceScores array is ignored.
            // TODO(sll): This, and the constraint that q.scores should be a
            // list of floats between 0.0 and 1.0, should be validated at the
            // time the question specification is entered.
            if (q.choiceScores && q.choiceScores.length == radioGroup.length) {
              score = q.choiceScores[i];
            } else {
              if (isCorrect) {
                score = 1;
                numCorrect++;
              }
            }

            userInputRecorded = true;
            userInput.push({
                'index': questionNum, 'type': 'choices', 'value': i,
                'correct': isCorrect});

            break;
          }
        }

        if (!userInputRecorded) {
          userInput.push({
              'index': questionNum, 'type': 'choices', 'value': null,
              'correct': isCorrect});
        }
      } else if (q.correctAnswerString) {
        var answerVal = $('#q' + questionNum).val();
        answerVal = answerVal.replace(/^\s+/,''); // trim leading spaces
        answerVal = answerVal.replace(/\s+$/,''); // trim trailing spaces

        isCorrect = (
            answerVal.toLowerCase() == q.correctAnswerString.toLowerCase());
        if (isCorrect) {
          score = 1;
          numCorrect++;
        }

        userInput.push({
            'index': questionNum, 'type': 'string', 'value': answerVal,
            'correct': isCorrect});
      } else if (q.correctAnswerRegex) {
        var answerVal = $('#q' + questionNum).val();
        answerVal = answerVal.replace(/^\s+/,''); // trim leading spaces
        answerVal = answerVal.replace(/\s+$/,''); // trim trailing spaces

        isCorrect = q.correctAnswerRegex.test(answerVal);
        if (isCorrect) {
          score = 1;
          numCorrect++;
        }

        userInput.push({
            'index': questionNum, 'type': 'regex', 'value': answerVal,
            'correct': isCorrect});
      } else if (q.correctAnswerNumeric) {
        // allow for some small floating-point leeway
        var answerNum = parseFloat($('#q' + questionNum).val());
        var EPSILON = 0.001;

        if ((q.correctAnswerNumeric - EPSILON <= answerNum) &&
            (answerNum <= q.correctAnswerNumeric + EPSILON)) {
          isCorrect = true;
          score = 1;
          numCorrect++;
        }

        userInput.push({
            'index': questionNum, 'type': 'numeric', 'value': answerNum,
            'correct': isCorrect});
      }

      scoreArray.push(score * weight);
      totalScore += score * weight;

      if (!isCorrect && q.lesson) {
        lessonsToRead.push(q.lesson);
      }
    });


    var numQuestions = assessment.questionsList.length;

    var percentScore = ((totalScore / totalWeight) * 100).toFixed(2);

    var assessmentType = getParamFromUrlByName('name') || 'unnamed assessment';

    var isSaveDraftReview = (!submitAnswers && assessmentGlobals.isReviewForm);

    // Show a confirmation message when submitting a peer-reviewed assessment,
    // since this action is non-reversible.
    if (!assessmentGlobals.isReviewForm && assessmentGlobals.grader == 'human') {
      if (!window.confirm(
        trans.SUBMIT_ASSIGNMENT_CONFIRMATION + trans.CONFIRMATION_EXPLANATION)) {
        return;
      }
    }

    // Show a confirmation message when submitting a review for another student's
    // assessment, since this action is non-reversible.
    if (assessmentGlobals.isReviewForm && !isSaveDraftReview) {
      if (!window.confirm(
        trans.SUBMIT_REVIEW_CONFIRMATION + trans.CONFIRMATION_EXPLANATION)) {
        return;
      }
    }

    if (submitAnswers || isSaveDraftReview) {
      // create a new hidden form, submit it via POST, and then delete it

      var myForm = document.createElement('form');
      myForm.method = 'post';

      // defaults to 'answer', which invokes AnswerHandler in ../../controllers/assessments.py
      myForm.action = assessmentGlobals.isReviewForm ? 'review' : 'answer';

      var myInput = null;

      myInput = document.createElement('input');
      myInput.setAttribute('name', 'assessment_type');
      myInput.setAttribute('value', assessmentType);
      myForm.appendChild(myInput);

      myInput = document.createElement('input');
      myInput.setAttribute('name', 'score');
      myInput.setAttribute('value', percentScore);
      myForm.appendChild(myInput);

      myInput = document.createElement('input');
      myInput.setAttribute('name', 'answers');
      myInput.setAttribute('value', JSON.stringify(userInput));
      myForm.appendChild(myInput);

      myInput = document.createElement('input');
      myInput.setAttribute('name', 'xsrf_token');
      myInput.setAttribute('value', assessmentXsrfToken);
      myForm.appendChild(myInput);

      if (assessmentGlobals.isReviewForm) {
        myInput = document.createElement('input');
        myInput.setAttribute('name', 'key');
        myInput.setAttribute('value', assessmentGlobals.key);
        myForm.appendChild(myInput);

        myInput = document.createElement('input');
        myInput.setAttribute('name', 'unit_id');
        myInput.setAttribute('value', assessmentGlobals.unitId);
        myForm.appendChild(myInput);

        myInput = document.createElement('input');
        myInput.setAttribute('name', 'is_draft');
        myInput.setAttribute('value', isSaveDraftReview);
        myForm.appendChild(myInput);
      }

      document.body.appendChild(myForm);
      myForm.submit();
      document.body.removeChild(myForm);
    } else {
      // send event to the server
      gcbAssessmentAudit({
          'type': 'assessment-' + assessmentType, 'values': userInput,
          'num_expected': numQuestions, 'num_submitted': userInput.length,
          'num_correct': numCorrect});

      // display feedback to the user
      var outtext = trans.YOUR_SCORE_TEXT + " " + percentScore + '% (' + totalScore.toFixed(0) + '/' +
          totalWeight + ').\n\n';

      if (lessonsToRead.length > 0) {
        outtext += trans.LESSONS_TO_REVIEW_TEXT + ': ' + lessonsToRead.join(', ') +
            '\n\n';
      }

      outtext += (percentScore >= 100 ? trans.PERFECT_SCORE_SAVE_TEXT : trans.GENERIC_SAVE_TEXT);
      $('#answerOutput').html(outtext);
    }
  }

  $('#checkAnswersBtn').click(function() {
      checkOrSubmitAnswers(false);
  });
  $('#saveDraftBtn').click(function() {
      checkOrSubmitAnswers(false);
  });
  $('#submitAnswersBtn').click(function() {
      checkOrSubmitAnswers(true);
  });
}

// wrap the value with a 'correct' tag
function correct(choiceStr) {
  return ['correct', choiceStr];
}

function checkText(id, regex) {
  var textValue = document.getElementById(id).value;
  textValue = textValue.replace(/^\s+/,''); // trim leading spaces
  textValue = textValue.replace(/\s+$/,''); // trim trailing spaces
  return regex.test(textValue);
}

// this code runs when the document fully loads
$(document).ready(function() {

  // send 'enter-page' event to the server
  try {
    gcbPageEventAudit({}, 'enter-page');
  } catch (e){}

  // hook click events of specific links
  $('#lessonNotesLink').click(function(evt) {
      gcbPageEventAudit({'href': evt.target.href}, 'click-link');
      return true;
  });

  // render the activity specified in the 'var activity' top-level variable
  // (if it exists)
  if (typeof activity != 'undefined') {
    var domRoot = $('#activityContents');
    if (domRoot.length) {
      renderActivity(activity, domRoot);
    }
  }
  // or render the assessment specified in the 'var assessment' top-level
  // variable (if it exists)
  else if (typeof assessment != 'undefined') {
    renderAssessment(assessment, $('#assessmentContents'));
  }

  // disable enter key on textboxes
  function stopRKey(evt) {
    var evt  = evt || (event || null);
    var node = evt.target || (evt.srcElement || null);
    if ((evt.keyCode == 13) && (node.type=='text')) {
      return false;
    }
  }
  $(document).keypress(stopRKey);
});

// this code runs when the document unloads
$(window).unload(function() {
  // send 'visit-page' event to the server
  try {
    // duration is in milliseconds
    gcbPageEventAudit({'duration': (new Date() - gcbBeginningOfTime)}, 'exit-page');
  } catch (e){}
});
