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
  preamble: '<b>This assessment addresses content in units 1, 2, and 3. You can try it as many times as you like. When you click "Check Answers," we will give you your score and give you a list of lessons to review. Please note that some of the assessment questions address functionality that does not work well on tablet computers.</b><br><br><p>You are getting a new puppy! Of course, you will have questions, and you\'ll probably turn to the web to look for answers.',

  // An ordered list of questions, with each question's type implicitly determined by the fields it possesses:
  //   choices              - multiple choice question (with exactly one correct answer)
  //   correctAnswerString  - case-insensitive string match
  //   correctAnswerRegex   - freetext regular expression match
  //   correctAnswerNumeric - freetext numeric match
  questionsList: [

    {questionHTML: 'You want to search exclusively within the Humane Society website (humanesociety.org) to find pages about puppy training.<br/><img src="assets/img/Image8.7.png" height="300" width="450" alt="search results for test question" title="search results for test question"><p>What would be the best query to type into the search box to see results like these?',
     choices: [correct('[site:humanesociety.org puppy training]'),
               '[humane society puppy training]',
               '[puppy training pages in humansociety.org website]',
               '[i need info about puppy training from humanesociety.org]',
               "I don't know"],
     // the (optional) lesson associated with this question, which is displayed as a suggestion
     // for further study if the student answers this question incorrectly.
     lesson: '3.1'},

    {questionHTML: 'You run two searches: [mountain dog] and [dog mountain]',
     choices: ['The top results would be the same.',
               correct('The top results would be different.'),
               "I don't know"],
     lesson: '1.5'},

    {questionHTML: 'You are considering a Golden Retriever and want to find out its drawbacks. You do a search for [golden retriever breed cons], and get a lot of results. After a while, reading the pages from different kennel clubs becomes a bit redundant and you would like to get rid of those results and just see pages by other types of authors. What do you add to the query [golden retriever breed cons] to exclude those results with the word kennel in them?',
     correctAnswerString: '-kennel',
     lesson: '3.3'},

    {questionHTML: 'You are talking to someone who has a dachshund that needs a home, and he describes it as being brindle. You wonder what that means. Which is the most efficient search to type into Google to help you find out?',
     correctAnswerRegex: /define(:| )brindle/i,
     lesson: '2.2'},

    {questionHTML: 'Another dog up for adoption is described as having a black patch on her occiput. You understand from context that it is a body part. What type of media would be most efficient to look in to get a quick idea of where the occiput is?',
     choices: ['Google Maps',
               'Google Discussions',
               'Google Blog Search',
               correct('Google Images'),
               "I don't know"],
     lesson: '2.3'},
  ],

  assessmentName: 'midcourse', // unique name submitted along with all of the answers
  checkAnswers: true,          // render a "Check your Answers" button to allow students to check answers prior to submitting?

  // formScript: 'answer',     // OPTIONAL: the Google App Engine Python script to run to submit answers, defaults to 'answer'
}

