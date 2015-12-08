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

var assessment = {
  // HTML to display at the start of the page
  preamble: 'When you write your review, please check that the student\'s response is relevant to the question asked. If not, answer \'No\' to the first question below.',

  questionsList: [
    {questionHTML: 'Did the student answer all parts of the question?',
     choices: ['Yes', 'No']},

    {questionHTML: 'Please provide feedback for the assignment author.',
     multiLine: true,
     correctAnswerRegex: /.*/i
    }
  ],

  // The assessmentName key is deprecated in v1.3 of Course Builder, and no
  // longer used. The assessment name should be set in the unit.csv file or via
  // the course editor interface.
  assessmentName: 'ReviewAssessmentExample',
  checkAnswers: false
}
