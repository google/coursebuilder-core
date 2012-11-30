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


// Usage instructions: Create a single array variable named 'activity'. This
// represents explanatory text and one or more questions to present to the
// student. Each element in the array should itself be either
//
// -- a string containing a set of complete HTML elements. That is, if the
//    string contains an open HTML tag (such as <form>), it must also have the
//    corresponding close tag (such as </form>). You put the actual question
//    text in a string.
//
// -- a JavaScript object representing the answer information for a question.
//    That is, the object contains properties such as the type of question, a
//    regular expression indicating the correct answer, a string to show in
//    case of either correct or incorrect answers or to show when the student
//    asks for help. For more information on how to specify the object, please
//    see http://code.google.com/p/course-builder/wiki/CreateActivities.

var activity = [

  '<table border="2"><tr><td><b>Search Tips:</b><p><ul><li>In the previous video, you learned how Google searches the web to find the results of your query. <li>Google looks for the word you typed in, but sometimes also looks for synonyms or related terms. Any words appearing in boldface type in your search results are terms Google associates with your search terms. For example, if you search for [kittens] you might see the word cats in boldface in your results.<li>Ads appear in response to some queries and are always labeled ads. <li>Aside from ads, website owners cannot pay to influence the placement of their website in the search results.</ul><p></tr></td></table><br>',

  'The next several questions explore what elements impact the order in which Google returns your results. Mark whether each statement is true or false, according to Matt Cutts:<p>',

  { questionType: 'multiple choice group',
    questionsList: [{questionHTML: 'Pages that have the words you type in, or synonyms for those words, are listed higher.',
                     choices: ['True', 'False'], correctIndex: 0},
                    {questionHTML: 'Pages with font size the same as you type into Google get listed first.',
                     choices: ['True', 'False'], correctIndex: 1},
                    {questionHTML: 'Pages where the words you typed in appear in the title or web address get listed higher.',
                     choices: ['True', 'False'], correctIndex: 0},
                    {questionHTML: 'Webmasters can get higher ranking in the results by paying Google money.',
                     choices: ['True', 'False'], correctIndex: 1},
                    {questionHTML: 'If the words you type in appear near each other on a page, it may get listed higher in your results.',
                     choices: ['True', 'False'], correctIndex: 1},
                    {questionHTML: 'Pages which are linked to by lots of other pages--especially other high quality pages--are listed higher.',
                     choices: ['True', 'False'], correctIndex: 0}],
    allCorrectOutput: 'Please scroll down for another activity.',
    someIncorrectOutput: 'Please try again.'},

  '<br><br><br>In the image below, identify the area(s) that are ads.<br><br><img src="assets/img/Image1.5.png" width="785" height="500" usemap="#Image1" border="0"><p>Where are the ads?<p>',

  { questionType: 'multiple choice',
    choices: [['A', false, 'Your answer is incorrect. Can you identify the two places where there are ads? Please try again.'],
              ['B', false, 'Your answer is incorrect. Can you identify the two places where there are ads? Please try again.'],
              ['C', false, 'Your answer is incorrect. Can you identify the two places where there are ads? Please try again.'],
              ['D', false, 'Your answer is incorrect. Can you identify the two places where there are ads? Please try again.'],
              ['A and B', false, 'Your answer is incorrect. Can you identify the two places where there are ads? Please try again.'],
              ['B and C', true, 'Your answer is correct! You have completed this activity.'],
              ['C and D', false, 'Your answer is incorrect. Can you identify the two places where there are ads? Please try again.']]}

];

