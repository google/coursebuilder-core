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
  preamble: 'Before we begin, we\'d like to learn a bit about what you know about search techniques. The goal of this pre-course assessment is not to judge or grade your skill, but to get a sense of what you know coming in, so that we can better understand what you gain from the course. To that end, please do not use Google to look for the answers--simply answer each question based on what you currently know.<br><br>Please note: During this assessment and the units that follow, you will often see words written inside square brackets [like this]. The brackets represent a search box like you see in Google, and the words inside the brackets are what you would type into the search box. So, if you see [golfcross rules], you can imagine seeing:<br/><img src="assets/img/Image11.1.png" height="50%" width="50%"><p>You would not type the brackets into Google, just the words inside them. <p>Thank you, and have fun!<br><br>',


  // An ordered list of questions, with each question's type implicitly determined by the fields it possesses:
  //   choices              - multiple choice question (with exactly one correct answer)
  //   correctAnswerString  - case-insensitive string match
  //   correctAnswerRegex   - freetext regular expression match
  //   correctAnswerNumeric - freetext numeric match
  questionsList: [
    {questionHTML: 'Which of the sections in the image below are advertisements?<p><img src="assets/img/Image0.1.png" alt="search results for test question" height=440 width=800 title="search results for test question">',
     choices: ["A and B", "D and B", correct("A and C"), "C and D", "I don't know"]
    },

    {questionHTML: 'When searching Google Images, you can drag an image into the search bar and find webpages where it appears online.',
     choices: [correct("True"), "False", "I don't know"]
    },

    {questionHTML: 'What would you type into the search box to get a top result that looks like this? If you do not know, enter "I don\'t know".<p><img src="assets/img/Image0.8.png" alt="search results for test question" height=100 width=600 title="search results for test question">',
     correctAnswerString: 'sunrise'
    },

    {questionHTML: 'What would you type into the search box to get a top result that looks like this? If you do not know, enter "I don\'t know".<p><p><img src="assets/img/Image0.9.png" alt="search results for test question" height=100 width=300 title="search results for test question">',
     correctAnswerRegex: /354\s*[+]\s*651/
    }
  ],

  // The assessmentName key is deprecated in v1.3 of Course Builder, and no
  // longer used. The assessment name should be set in the unit.csv file or via
  // the course editor interface.
  assessmentName: 'Pre', // unique name submitted along with all of the answers

  checkAnswers: false    // render a "Check your Answers" button to allow students to check answers prior to submitting?
}
