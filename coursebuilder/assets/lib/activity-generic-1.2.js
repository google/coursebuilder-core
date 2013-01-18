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

// highlight the correct answer
var highlightColor = '#3BB9FF';

var globallyUniqueTag = 0; // each question should have a unique tag

function getFreshTag() {
  globallyUniqueTag++;
  return globallyUniqueTag;
}

// controls sending events to the server; off by default; override to enable
var gcbCanPostEvents = false;

// various XSRF tokens
var eventXsrfToken = '';
var assessmentXsrfToken = '';

function gcbActivityAudit(dict) {
  gcbAudit(dict, 'attempt-activity');
}

function gcbAssessmentAudit(dict) {
  gcbAudit(dict, 'attempt-assessment');
}

function gcbAudit(dict, source) {
  if (gcbCanPostEvents) {
    dict['location'] = '' + window.location;
    var request = {
        'source': source,
        'payload': JSON.stringify(dict),
        'xsrf_token': eventXsrfToken};
    $.ajax({
        url: 'rest/events',
        type: 'POST',
        data: {'request': JSON.stringify(request)},
        success: function(){},
        error:function(){}
    });
  }
}

// 'choices' is a list of choices, where each element is:
//    [choice label, is correct? (boolean), output when this choice is submitted]
// 'domRoot' is the dom element to append HTML onto
// 'index' is the index of this activity in the containing list
function generateMultipleChoiceQuestion(choices, domRoot, index) {
  var tag = getFreshTag();
  var radioButtonGroupName = 'q' + tag;

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
  domRoot.append('<p/><button class="gcb-button gcb-button-primary" ' +
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

  // create questions
  $.each(questionsList, function(i, q) {
    var tag = getFreshTag();
    used_tags.push(tag);

    var radioButtonGroupName = 'q' + tag;

    // create question HTML
    domRoot.append(q.questionHTML);
    domRoot.append('<br>');

    // create radio buttons
    $.each(q.choices, function(j, choiceLabel) {
      var buttonId = radioButtonGroupName + '-' + i + '-' + j;
      if (j == q.correctIndex) {
        domRoot.append(
            '<span class="correct_' + tag + '">' +
            '<input type="radio" name="' + radioButtonGroupName + '" ' +
            'id="' + buttonId + '" value="correct"> ' +
            '<label for="' + buttonId + '">' + choiceLabel + '</label></span>');
      }
      else {
        domRoot.append(
            '<input type="radio" name="' + radioButtonGroupName + '" ' +
            'id="' + buttonId + '"> ' +
            '<label for="' + buttonId + '">' + choiceLabel + '</label>');
      }
      domRoot.append('<br>');
    });

    domRoot.append('<p/>');

  });


  var toplevel_tag = getFreshTag();

  domRoot.append(
      '<p/><button class="gcb-button gcb-button-primary" id="submit_' +
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
    var numCorrect = 0;
    var numChecked = 0;
    answers = []

    $.each(questionsList, function(ind, q) {
      var tag = used_tags[ind];
      var radioButtonGroupName = 'q' + tag;
      var choiceInputs = $('input[name=' + radioButtonGroupName + ']');

      var userInputRecorded = false;
      for (var i = 0; i < choiceInputs.length; i++) {
        var isChecked = choiceInputs[i].checked;
        var isCorrect = i == q.correctIndex
        if (isChecked) {
          numChecked++;
          if (isCorrect) {
             numCorrect++;
          }

          userInputRecorded = true;
          answers.push({'index': ind, 'value': i, 'correct': isCorrect});
        }
      }

      if (!userInputRecorded) {
        answers.push({'index': ind, 'value': null, 'correct': isCorrect});
      }
    });

    gcbActivityAudit({
        'index': index, 'type': 'activity-group', 'values': answers,
        'num_expected': questionsList.length,
        'num_submitted': numChecked, 'num_correct': numCorrect});

    if (numCorrect == questionsList.length) {
      $.each(used_tags, function(i, t) {
        $('.correct_' + t).css('background-color', highlightColor);
      });
      $('#output_' + toplevel_tag).val(
          trans.ALL_CORRECT_TEXT + ' ' + allCorrectOutput);
      $('#output_' + toplevel_tag).focus();
    }
    else {
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

  domRoot.append(
      '&nbsp;&nbsp;<input type="text" style="width: 400px; ' +
      'class="alphanumericOnly" id="input_' + tag + '">');
  if (correctAnswerOutput && incorrectAnswerOutput) {
    domRoot.append('<p/><button class="gcb-button gcb-button-primary" ' +
        'id="submit_' + tag + '">' + trans.CHECK_ANSWER_TEXT + '</button>');
  }
  if (showAnswerOutput) {
    domRoot.append(
        '<p/><button class="gcb-button gcb-button-primary" ' +
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
        generateMultipleChoiceQuestion(e.choices, domRoot, i);
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

  domRoot.append('<ol></ol>');

  var questionsOL = domRoot.find('ol');

  $.each(assessment.questionsList, function(questionNum, q) {
    questionsOL.append('<li></li>');

    var curLI = questionsOL.find('li:last');
    curLI.append(q.questionHTML);
    curLI.append('<p/>');

    // Dispatch to specialized handler depending on the existence of particular fields:
    //   choices              - multiple choice question (with exactly one correct answer)
    //   correctAnswerString  - case-insensitive substring match
    //   correctAnswerRegex   - freetext regular expression match
    //   correctAnswerNumeric - freetext numeric match
    if (q.choices) {
      $.each(q.choices, function(i, c) {
        var buttonId = 'q' + questionNum + '-' + i;
        if (typeof c == 'string') {
          // incorrect choice
          curLI.append('<input type="radio" name="q' + questionNum + '" id="' +
              buttonId + '">&nbsp;<label for="' + buttonId + '">' + c + '</label><br>');
        }
        else {
          // wrapped in correct() ...
          if (c[0] != 'correct') {
            alert('Error: Malformed question.');
          }
          // correct choice
          curLI.append('<input type="radio" name="q' + questionNum + '" id="' +
              buttonId + '" value="correct">&nbsp;<label for="' + buttonId + '">' +
              c[1] + '</label><br>');
        }
      });
    } else if (q.correctAnswerString || q.correctAnswerRegex || q.correctAnswerNumeric) {
      curLI.append('Answer:&nbsp;&nbsp;<input type="text" class="alphanumericOnly" ' +
          'style="border-style: solid; border-color: black; border-width: 1px;" ' +
          'id="q' + questionNum + '">');
    } else {
      alert('Error: Invalid question type.');
    }

    curLI.append('<br><br>');
  });


  if (assessment.checkAnswers) {
    domRoot.append(
        '<button type="button" class="gcb-button gcb-button-primary" id="checkAnswersBtn">' +
        trans.CHECK_ANSWERS_TEXT + '</button><p/>');
    domRoot.append('<p/><textarea style="width: 600px; height: 120px;" ' +
        'readonly="true" id="answerOutput"></textarea>');
  }
  domRoot.append(
      '<br><button type="button" class="gcb-button gcb-button-primary" id="submitAnswersBtn">' +
      trans.SAVE_ANSWERS_TEXT + '</button>');


  function checkOrSubmitAnswers(submitAnswers) {
    $('#answerOutput').html('');

    var scoreArray = [];
    var lessonsToRead = [];
    var userInput = [];

    $.each(assessment.questionsList, function(questionNum, q) {
      var isCorrect = false;

      if (q.choices) {
        var userInputRecorded = false;
        var radioGroup = document.assessment['q' + questionNum];
        for (var i = 0; i < radioGroup.length; i++) {
          if (radioGroup[i].checked) {
            isCorrect = radioGroup[i].value == 'correct';

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
      }
      else if (q.correctAnswerString) {
        var answerVal = $('#q' + questionNum).val();
        answerVal = answerVal.replace(/^\s+/,''); // trim leading spaces
        answerVal = answerVal.replace(/\s+$/,''); // trim trailing spaces

        isCorrect = (
            answerVal.toLowerCase() == q.correctAnswerString.toLowerCase());

        userInput.push({
            'index': questionNum, 'type': 'string', 'value': answerVal,
            'correct': isCorrect});
      }
      else if (q.correctAnswerRegex) {
        var answerVal = $('#q' + questionNum).val();
        answerVal = answerVal.replace(/^\s+/,''); // trim leading spaces
        answerVal = answerVal.replace(/\s+$/,''); // trim trailing spaces

        isCorrect = q.correctAnswerRegex.test(answerVal);

        userInput.push({
            'index': questionNum, 'type': 'regex', 'value': answerVal,
            'correct': isCorrect});
      }
      else if (q.correctAnswerNumeric) {
        // allow for some small floating-point leeway
        var answerNum = parseFloat($('#q' + questionNum).val());
        var EPSILON = 0.001;

        if ((q.correctAnswerNumeric - EPSILON <= answerNum) &&
            (answerNum <= q.correctAnswerNumeric + EPSILON)) {
          isCorrect = true;
        }

        userInput.push({
            'index': questionNum, 'type': 'numeric', 'value': answerNum,
            'correct': isCorrect});
      }

      scoreArray.push(isCorrect);

      if (!isCorrect && q.lesson) {
        lessonsToRead.push(q.lesson);
      }
    });


    var numQuestions = assessment.questionsList.length;

    var numCorrect = 0;
    $.each(scoreArray, function(i, e) {
      if (e) {
        numCorrect++;
      }
    });

    var score = ((numCorrect / numQuestions) * 100).toFixed(2);

    var assessmentType = assessment.assessmentName || 'unnamed assessment';
    if (submitAnswers) {
      // create a new hidden form, submit it via POST, and then delete it

      var myForm = document.createElement('form');
      myForm.method = 'post';

      // defaults to 'answer', which invokes AnswerHandler in ../../controllers/assessments.py
      myForm.action = assessment.formScript || 'answer';

      var myInput = null;

      myInput= document.createElement('input');
      myInput.setAttribute('name', 'assessment_type');
      myInput.setAttribute('value', assessmentType);
      myForm.appendChild(myInput);

      myInput = document.createElement('input');
      myInput.setAttribute('name', 'score');
      myInput.setAttribute('value', score);
      myForm.appendChild(myInput);

      myInput = document.createElement('input');
      myInput.setAttribute('name', 'answers');
      myInput.setAttribute('value', JSON.stringify(userInput));
      myForm.appendChild(myInput);

      myInput = document.createElement('input');
      myInput.setAttribute('name', 'xsrf_token');
      myInput.setAttribute('value', assessmentXsrfToken);
      myForm.appendChild(myInput);

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
      var outtext = trans.YOUR_SCORE_TEXT + " " + score + '% (' + numCorrect + '/' +
          numQuestions + ').\n\n';

      if (lessonsToRead.length > 0) {
        outtext += trans.LESSONS_TO_REVIEW_TEXT + ': ' + lessonsToRead.join(', ') +
            '\n\n';
      }

      outtext += (score >= 100 ? trans.PERFECT_SCORE_SAVE_TEXT : trans.GENERIC_SAVE_TEXT);
      $('#answerOutput').html(outtext);
    }
  }

  $('#checkAnswersBtn').click(function() {
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

// this code runs when the document fully loads:
$(document).ready(function() {
  // render the activity specified in the 'var activity' top-level variable
  // (if it exists)
  if (typeof activity != 'undefined') {
    renderActivity(activity, $('#activityContents'));
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
