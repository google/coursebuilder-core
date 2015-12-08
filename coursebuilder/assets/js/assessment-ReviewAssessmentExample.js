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
  preamble: 'Solve the problem below by using concepts from at least three Power Search lessons. Record your experience in a Google doc.<br><br><strong>Problem</strong>: Plan a 3-day trip to a destination you have never visited. Where will you go? Why?',

  questionsList: [
    {questionHTML: 'Please write your response in a Google doc, and paste the link to the doc in the answer box below. You will need to ensure that your doc can be viewed by reviewers; please see this <a href="https://support.google.com/drive/bin/answer.py?hl=en&answer=2494822&topic=2816927&rd=1">help page</a> for instructions on how to do this.',
     correctAnswerRegex: /.*/i
    },

    {questionHTML: 'How many Power Search concepts did you use in your writeup?',
     choices: ['0 - 2', '3', '4 -- 5', 'More than 5']},

    {questionHTML: 'List the Power Search concepts you used.',
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
