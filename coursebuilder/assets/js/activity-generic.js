// Copyright 2012 Google Inc. All Rights Reserved.
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
var highlightColor = "#3BB9FF";


var globally_unique_tag = 1; // each question should have a unique tag

function get_fresh_tag() {
  var t = globally_unique_tag
  globally_unique_tag++;
  return t;
}


// 'choices' is a list of choices, where each element is:
//    [choice label, is correct? (boolean), output when this choice is submitted]
// 'domRoot' is the dom element to append HTML onto
function generateMultipleChoiceQuestion(choices, domRoot) {
  var tag = get_fresh_tag();

  var radioButtonGroupName = 'q' + tag;

  // create radio buttons
  $.each(choices, function(i, elt) {
    var label = elt[0];
    var isCorrect = elt[1];
    if (isCorrect) {
      domRoot.append('<span class="correct_' + tag + '"><input type="radio" name="' + radioButtonGroupName + '" value="correct"/> ' + label + '</span>');
    }
    else {
      domRoot.append('<input type="radio" name="' + radioButtonGroupName + '"/> ' + label);
    }
    domRoot.append('<br/>');
  });

  domRoot.append('<br/>');
	domRoot.append('<p/><a class="gcb-button gcb-button-primary" id="submit_' + tag + '">Check Answer</a>');
  domRoot.append('<p/><textarea style="width: 600px; height: 50px;" readonly="true" id="output_' + tag + '"></textarea>');


  var choiceInputs = $("input[name=" + radioButtonGroupName + "]");

  // clear output and highlighting whenever a checkbox is clicked
  choiceInputs.click(function() {
    $('.correct_' + tag).css('background-color', '');
    $('#output_' + tag).val('');
  });

  // check inputs and update output
  $('#submit_' + tag).click(function() {
    var answerChosen = false;
    for (var i = 0; i < choiceInputs.length; i++) {
      var isCorrect = choices[i][1];
      var outputMsg = choices[i][2];

      var isChecked = choiceInputs[i].checked;
      if (isChecked) {
        $('#output_' + tag).val(outputMsg);
        if (isCorrect) {
          $('.correct_' + tag).css('background-color', highlightColor);
        }

        answerChosen = true;
      }
    }

    if (!answerChosen) {
      $('#output_' + tag).val('Please click one of the buttons for your answer.');
    }
  });
}


// Generate a collection of multiple choice questions
// 'params' is an object containing parameters
// 'domRoot' is the dom element to append HTML onto
function generateMultipleChoiceGroupQuestion(params, domRoot) {

  // 'questionsList' is an ordered list of questions, where each element is:
  //   {questionHTML: <HTML of question>, choices: <list of choice labels>, correctIndex: <index of correct choice>}
  // 'allCorrectOutput' is what to display when ALL of the answers are correct
  // 'someIncorrectOutput' is what to display when not all of the answers are correct
  var questionsList = params.questionsList;
  var allCorrectOutput = params.allCorrectOutput;
  var someIncorrectOutput = params.someIncorrectOutput;

  var used_tags = [];

  // create questions
  $.each(questionsList, function(xxx, q) {
    var tag = get_fresh_tag();
    used_tags.push(tag);

    var radioButtonGroupName = 'q' + tag;

    // create question HTML
    domRoot.append(q.questionHTML);
    domRoot.append('<br/>');

    // create radio buttons
    $.each(q.choices, function(i, choiceLabel) {
      if (i == q.correctIndex) {
        domRoot.append('<span class="correct_' + tag + '"><input type="radio" name="' + radioButtonGroupName + '" value="correct"/> ' + choiceLabel + '</span>');
      }
      else {
        domRoot.append('<input type="radio" name="' + radioButtonGroupName + '"/> ' + choiceLabel);
      }
      domRoot.append('<br/>');
    });

    domRoot.append('<p/>');

  });


  var toplevel_tag = get_fresh_tag();

	domRoot.append('<p/><a class="gcb-button gcb-button-primary" id="submit_' + toplevel_tag + '">Check your answers</a>');
  domRoot.append('<p/><textarea style="width: 600px; height: 100px;" readonly="true" id="output_' + toplevel_tag + '"></textarea>');


  // clear output and highlighting for ALL questions whenever any checkbox is clicked
  $.each(questionsList, function(i, q) {
    var tag = used_tags[i];
    var radioButtonGroupName = 'q' + tag;
    var choiceInputs = $("input[name=" + radioButtonGroupName + "]");

    choiceInputs.click(function() {
      $.each(used_tags, function(xxx, t) {
        $('.correct_' + t).css('background-color', '');
      });
      $('#output_' + toplevel_tag).val('');
    });
  });


  // handle question submission
  $('#submit_' + toplevel_tag).click(function() {
    var numCorrect = 0;

    $.each(questionsList, function(i, q) {
      var tag = used_tags[i];
      var radioButtonGroupName = 'q' + tag;
      var choiceInputs = $("input[name=" + radioButtonGroupName + "]");

      for (var i = 0; i < choiceInputs.length; i++) {
        var isChecked = choiceInputs[i].checked;
        if (isChecked && (i == q.correctIndex)) {
          numCorrect++;
        }
      }
    });

    if (numCorrect == questionsList.length) {
      $.each(used_tags, function(i, t) {
        $('.correct_' + t).css('background-color', highlightColor);
      });
      $('#output_' + toplevel_tag).val("All your answers are correct! " + allCorrectOutput);
    }
    else {
      $('#output_' + toplevel_tag).val("You got " + numCorrect + " out of " + questionsList.length + " questions correct. " + someIncorrectOutput);
    }
  });
}


// 'params' is an object containing parameters (some optional)
// 'domRoot' is the dom element to append HTML onto
function generateFreetextQuestion(params, domRoot) {

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
  var showAnswerPrompt = params.showAnswerPrompt ?  params.showAnswerPrompt : 'Skip & Show Answer'; // optional parameter
  var outputHeight = params.outputHeight ?  params.outputHeight : '50px'; // optional parameter


  var tag = get_fresh_tag();

  domRoot.append('&nbsp;&nbsp;<input type="text" style="width: 400px; class="alphanumericOnly" id="input_' + tag + '"/>');
  if (correctAnswerOutput && incorrectAnswerOutput) {
    domRoot.append('<p/><a class="gcb-button gcb-button-primary" id="submit_' + tag + '">Check Answer</a>');
  }
  if (showAnswerOutput) {
    domRoot.append('<p/><a class="gcb-button gcb-button-primary" id="skip_and_show_' + tag + '">' + showAnswerPrompt + '</a>');
  }
  domRoot.append('<p/><textarea style="width: 600px; height: ' + outputHeight + ';" readonly="true" id="output_' + tag + '"></textarea>');


  // we need to wait until ALL elements are in the DOM before binding event handlers

  $('#input_' + tag).focus(function() {
    $('#output_' + tag).val('');
  });
  
  if (correctAnswerOutput && incorrectAnswerOutput) {
    $('#submit_' + tag).click(function() {

      var textValue = $('#input_' + tag).val();
      textValue = textValue.replace(/^\s+/,''); //trim leading spaces
      textValue = textValue.replace(/\s+$/,''); //trim trailing spaces

      // check specific words: killer whale
      var isCorrect = correctAnswerRegex.test(textValue);
      if (isCorrect) {
        $('#output_' + tag).val(correctAnswerOutput);
      }
      else {
        $('#output_' + tag).val(incorrectAnswerOutput);
      }
    });
  }

  if (showAnswerOutput) {
    $('#skip_and_show_' + tag).click(function() {
      $('#output_' + tag).val(showAnswerOutput);
    });
  }
}


// Takes a list of HTML element strings and special question objects and renders HTML onto domRoot
//
// The main caveat here is that each HTML string must be a FULLY-FORMED HTML element that
// can be appended wholesale to the DOM, not a partial element.
function renderActivity(contentsLst, domRoot) {
  $.each(contentsLst, function(i, e) {
    if (typeof e == 'string') {
      domRoot.append(e);
    }
    else {
      // dispatch on type:
      if (e.questionType == 'multiple choice') {
        generateMultipleChoiceQuestion(e.choices, domRoot);
      }
      else if (e.questionType == 'multiple choice group') {
        generateMultipleChoiceGroupQuestion(e, domRoot);
      }
      else if (e.questionType == 'freetext') {
        generateFreetextQuestion(e, domRoot);
      }
      else {
        alert("Error in renderActivity: e.questionType is not in {'multiple choice', 'multiple choice group', 'freetext'}");
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
        if (typeof c == 'string') {
          // incorrect choice
          curLI.append('<input type="radio" name="q' + questionNum + '"/>&nbsp;' + c + '<br/>');
        }
        else {
          // wrapped in correct() ...
          if (c[0] != 'correct') {
            alert('Error: Malformed question.');
          }
          // correct choice
          curLI.append('<input type="radio" name="q' + questionNum + '" value="correct"/>&nbsp;' + c[1] + '<br/>');
        }
      });
    }
    else if (q.correctAnswerString || q.correctAnswerRegex || q.correctAnswerNumeric) {
      curLI.append('Answer:&nbsp;&nbsp;<input type="text" class="alphanumericOnly" style="border-style: solid; border-color: black; border-width: 1px;" id="q' + questionNum + '"/>');
    }
    else {
      alert("Error: Invalid question type.");
    }

    curLI.append('<br/><br/>');
  });


  if (assessment.checkAnswers) {
    domRoot.append('<a class="gcb-button gcb-button-primary" id="checkAnswersBtn">Check your Answers</a><p/>');
    domRoot.append('<p/><textarea style="width: 600px; height: 120px;" readonly="true" id="answerOutput"></textarea>');
  }
  domRoot.append('<br/><a class="gcb-button gcb-button-primary" id="submitAnswersBtn">Save Answers</a>');


  function checkOrSubmitAnswers(submitAnswers) {
    $('#answerOutput').html('');

    var scoreArray = [];
    var lessonsToRead = [];
    
    $.each(assessment.questionsList, function(questionNum, q) {
      var isCorrect = false;

      if (q.choices) {
        isCorrect = checkQuestionRadioSimple(document.assessment['q' + questionNum]);
      }
      else if (q.correctAnswerString) {
        var answerVal = $('#q' + questionNum).val();
        answerVal = answerVal.replace(/^\s+/,''); // trim leading spaces
        answerVal = answerVal.replace(/\s+$/,''); // trim trailing spaces

        isCorrect = (answerVal.toLowerCase() == q.correctAnswerString.toLowerCase());
      }
      else if (q.correctAnswerRegex) {
        var answerVal = $('#q' + questionNum).val();
        answerVal = answerVal.replace(/^\s+/,''); // trim leading spaces
        answerVal = answerVal.replace(/\s+$/,''); // trim trailing spaces

        // check specific words: killer whale
        isCorrect = q.correctAnswerRegex.test(answerVal);
      }
      else if (q.correctAnswerNumeric) {
        // allow for some small floating-point leeway
        var answerNum = parseFloat($('#q' + questionNum).val());
        var EPSILON = 0.001;

        if ((q.correctAnswerNumeric - EPSILON <= answerNum) &&
            (answerNum <= q.correctAnswerNumeric + EPSILON)) {
          isCorrect = true;
        }
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


    if (submitAnswers) {
      // create a new hidden form, submit it via POST, and then delete it

      var myForm = document.createElement("form");
      myForm.method = "post";

      // defaults to 'answer', which invokes AnswerHandler in ../../controllers/lessons.py
      myForm.action = assessment.formScript ? assessment.formScript : "answer";

      var assessmentType = assessment.assessmentName ? assessment.assessmentName : "unnamed assessment";

      var myInput = null;
      
      myInput= document.createElement("input");
      myInput.setAttribute("name", "assessment_type");
      myInput.setAttribute("value", assessmentType);
      myForm.appendChild(myInput);

      // create a form entry for each question/result pair
      $.each(scoreArray, function(i, val) {
        myInput = document.createElement("input");
        myInput.setAttribute("name", i);
        myInput.setAttribute("value", val);
        myForm.appendChild(myInput);
      });

      myInput = document.createElement("input");
      myInput.setAttribute("name", "num_correct");
      myInput.setAttribute("value", numCorrect);
      myForm.appendChild(myInput);

      myInput = document.createElement("input");
      myInput.setAttribute("name", "num_questions");
      myInput.setAttribute("value", numQuestions);
      myForm.appendChild(myInput);

      myInput = document.createElement("input");
      myInput.setAttribute("name", "score");
      myInput.setAttribute("value", score);
      myForm.appendChild(myInput);

      document.body.appendChild(myForm);
      myForm.submit();
      document.body.removeChild(myForm);
    }
    else {
      // display feedback without submitting any data to the backend

      var outtext = "You received " + score + "% (" + numCorrect + "/" + numQuestions + ") on this assessment.\n\n";

      if (lessonsToRead.length > 0) {
        outtext += "Here are lessons you could review to improve your score: " + lessonsToRead.join(', ') + "\n\n";
      }

      if (score < 100) {
        outtext += "Press the 'Save Answers' button below to save your scores. You can also edit your answers above before clicking 'Save Answers'.";
      }
      else {
        outtext += "Congratulations! Press the 'Save Answers' button to submit your grade.";
      }

      $('#answerOutput').html(outtext);
    }

  }


  $('#checkAnswersBtn').click(function() {checkOrSubmitAnswers(false);});
  $('#submitAnswersBtn').click(function() {checkOrSubmitAnswers(true);});
}

// wrap the value with a 'correct' tag
function correct(choiceStr) {
  return ['correct', choiceStr];
}


// check a radio button answer - simple; return 1 if correct button checked
function checkQuestionRadioSimple(radioGroup) {
  for (i=0; i<radioGroup.length; i++) {
    if (radioGroup[i].checked) {
      if (radioGroup[i].value == "correct") {
        return true;
      }
      else {
        return false;
      }
    }
  }
  return false;
}


function checkText(id, regex) {
  var textValue = document.getElementById(id).value;
  textValue = textValue.replace(/^\s+/,''); // trim leading spaces
  textValue = textValue.replace(/\s+$/,''); // trim trailing spaces
  // check specific words: killer whale
  return regex.test(textValue);
}


// this code runs when the document fully loads:
$(document).ready(function() {
  // render the activity specified in the 'var activity' top-level variable
  // (if it exists)
  if (typeof activity != 'undefined') {
    renderActivity(activity, $('#activityContents'));
  }
  // or render the assessment specified in the 'var assessment' top-level variable
  // (if it exists)
  else if (typeof assessment != 'undefined') {
    renderAssessment(assessment, $('#assessmentContents'));
  }


  // disable enter key on textboxes
  function stopRKey(evt) {
    var evt  = (evt) ? evt : ((event) ? event : null);
    var node = (evt.target) ? evt.target : ((evt.srcElement) ? evt.srcElement : null);
    if ((evt.keyCode == 13) && (node.type=="text")) { return false; }
  }
  $(document).keypress(stopRKey);
});

