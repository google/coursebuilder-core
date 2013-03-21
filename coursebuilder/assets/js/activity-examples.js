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


// sample activities

var activity = [

  '<p>This is just some <i>HTML</i> text!</p>',

  // here is a simple multiple choice question where only one answer is valid
  { questionType: 'multiple choice',
    questionHTML: '<p>What letter am I thinking about now?</p>',
    choices: [
          ['A', false, '"A" is wrong, try again.'],
          ['B', true, '"B" is correct!'],
          ['C', false, '"C" is wrong, try again.'],
          ['D', false, '"D" is wrong, try again.']
    ]
  },

  // here is a regex-validating question that requires you to type in the answer
  { questionType: 'freetext',
    questionHTML: '<p>What color is the snow?</p>',
    correctAnswerRegex: /white/i,
    correctAnswerOutput: 'Correct!',
    incorrectAnswerOutput: 'Try again.',
    showAnswerOutput: 'Our search expert says: white!' },

  // here is a set of multiple choice questions, some have several valid answers;
  // 'multiSelect' controls whether student must check all the right answers
  // (true) or just one of the correct answers (false); the default is true
  // 'allCorrectMinCount' controls how many questions must be answered correctly
  // for the entire question group to be considered completed successfully
  { questionType: 'multiple choice group',
    questionGroupHTML: '<p>This section will test you on colors and numbers.</p>',
    questionsList: [
          {questionHTML: 'Pick all <i>odd</i> numbers:',
           choices: ['1', '2', '3', '4', '5'], correctIndex: [0, 2, 4]},
          {questionHTML: 'Pick one <i>even</i> number:',
           choices: ['1', '2', '3', '4', '5'], correctIndex: [1, 3],
           multiSelect: false},
          {questionHTML: 'What color is the sky?',
           choices: ['#00FF00', '#00FF00', '#0000FF'], correctIndex: 2}
    ],
    allCorrectMinCount: 2,
    allCorrectOutput: 'Great job! You know the material well.',
    someIncorrectOutput: 'You must answer at least two questions correctly.'
  }

];
