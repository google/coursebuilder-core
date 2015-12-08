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
  preamble: '<b>This assessment addresses content in units 1-6. You can try it as many times as you like. When you click "Check Answers," we will give you your score and give you a list of lessons to review. Please note that some of the assessment questions address functionality that does not work well on tablet computers.</b><br><br>',

  // An ordered list of questions, with each question's type implicitly determined by the fields it possesses:
  //   choices              - multiple choice question (with exactly one correct answer)
  //   correctAnswerString  - case-insensitive string match
  //   correctAnswerRegex   - freetext regular expression match
  //   correctAnswerNumeric - freetext numeric match
  questionsList: [
    {questionHTML: 'Where will the Summer Olympics of 2016 be held?', // question can be plain text or arbitrary HTML
     choices: ['Chicago', 'Tokyo', correct('Rio de Janeiro'), 'Madrid', 'I don\'t know'],
     // the (optional) lesson associated with this question, which is displayed as a suggestion
     // for further study if the student answers this question incorrectly.
     lesson: '1.4'},

  {questionHTML: 'Your friends know that you are interested in taking this trip to the 2016 Olympics, and one sends you the following post: "Hey! Know you are planning your trip to the Olympics. Thought you might like to see this." He did not identify the picture in any way, and he is not available right now for you to ask him.<p><img src="http://www.loc.gov/rr/main/images/tugwar.jpg"></p><p>What is the title of the work in which this picture was published?</p>',
     choices: ['The Olympic Games Being a Short History of the Olympic Movement From 1896 up to the Present Day, by Theodore Andrea Cook',
               'The Olympic Games: Daily Official Program, by the Amateur Athletic Union of the United States',
               'The Olympic games at Athens, 1906, by James Edward Sullivan',
               correct('The Olympic Games 1904, by Charles Lucas'),
               "I don't know"],
      lesson: '4.1'},

    {questionHTML: '<font style="font-style:italic;">The Encyclopedia of the Modern Olympic Movement</font>, by John E. Findling and Kimberly D. Pelle, reports that the author of this work was an olympic trainer. From where did he watch the competition for the athlete he coached?',
     choices: ['He listened to it on the radio from his hospital bed.',
               correct('He watched it from the back of the car leading the race.'),
               'He was stuck in a traffic jam and missed it completely.',
               "He watched it from the stands with the winner's mother.",
               "I don't know"],
      lesson: '2.5'},

    {questionHTML: 'You decide to attend the Summer Olympics and find yourself surrounded by Portuguese speakers. How would you say, "Is there a cheap restaurant around here?" in Portuguese?"<br/>[this version of the question uses a case-insensitive string match]',
     correctAnswerString: 'existe um rest?',
     lesson: '4.5'},

    {questionHTML: 'You decide to attend the Summer Olympics and find yourself surrounded by Portuguese speakers. How would you say, "Is there a cheap restaurant around here?" in Portuguese?"<br/>[this version of the question uses a regular expression match]',
     correctAnswerRegex: /existe um rest?/i,
     lesson: '4.5'},

    {questionHTML: 'This is an example of a numeric freetext question. What is 3.2 + 4.7?',
     correctAnswerNumeric: 7.9,
     lesson: '99.99'},

    {questionHTML: 'You recall that in past years, the Olympics have included some sports that were popular in the host country. Although medals awarded in these events were not official, they were often fun to watch. You try searching for the topic, and get these results:<p><img src="assets/img/Image7.7.png" width="500" height="500" alt="search results for test question" title="search results for test question"><br/>What term do these results suggest that would give you a more focused query on this topic?',
     choices: [correct('Demonstration sport'),
               'Masters Athletics',
               'Olympic Sports',
               'Olympic Games',
               "I don't know"],
     lesson: '2.2'}
  ],

  // The assessmentName key is deprecated in v1.3 of Course Builder, and no
  // longer used. The assessment name should be set in the unit.csv file or via
  // the course editor interface.
  assessmentName: 'Fin', // unique name submitted along with all of the answers

  checkAnswers: true     // render a "Check your Answers" button to allow students to check answers prior to submitting?
}

