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


// When the assessment page loads, activity-generic.js will render the contents
// of the 'assessment' variable into the enclosing HTML webpage.

// For information on modifying this page, see
// https://code.google.com/p/course-builder/wiki/CreateAssessments.


var assessment = {
  // HTML to display at the start of the page
  preamble: '<b>This assessment is peer-reviewed.</b><br><br>From Kee Malesky, of National Public Radio: <br><br>I was asked recently to find reputable sources for the following statement: "During the glory days of radio, it was illegal to mimic the voice of the US president." Was there actually a law prohibiting that? Or was it just a White House policy, and not a legal issue?',

  questionsList: [
    {questionHTML: 'Was it law or policy?',
     choices: ['Law', 'Policy']},

    {questionHTML: 'Explain how you solved the problem. Write your answers in a Google Doc, and include the link to the doc in the space below.',
     correctAnswerRegex: /.*/i
    }
  ],

  // The assessmentName key is deprecated in v1.3 of Course Builder, and no
  // longer used. The assessment name should be set in the unit.csv file or via
  // the course editor interface.
  assessmentName: 'ReviewAssessmentExample',
  checkAnswers: false
}
