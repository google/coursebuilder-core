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

  '<table border="2"><tr><td><b>Search Tips:</b><p><ul><li>Translate words, sentences, and pages by using translate.google.com.<li>Search in foreign languages using English by clicking "More search tools" on the left panel of your results page, then select "Translated foreign pages". This feature chooses the best language in which to search and delivers results translated back into English.</ul></tr></td></table>',

  '<p><b>1.</b> Please find the answer this question: Apa warna pada bendera Indonesia?</p>',


  { questionType: 'multiple choice',
    choices: [['Red, white, and blue', false, 'Try again. How can you find out what this question means in English? Did you go to translate.google.com? Hint: this question is in Indonesian.'],
              ['Yellow and green', false, 'Try again. How can you find out what this question means in English? Did you go to translate.google.com? Hint: this question is in Indonesian.'],
              ['Red and green', false, 'Try again. How can you find out what this question means in English? Did you go to translate.google.com? Hint: this question is in Indonesian.'],
              ['Red and white', true, 'Correct! The Indonesian flag is red and white. This question was complex: \n1) Search for [google translate]. \n2) Paste this question into the Translate box, to learn that it means: What color is the flag of Indonesia? \n3) Search Google for [flag indonesia]. \n4) See an image of the flag and learn that it is red and white.']]},

  '<p><b>2.</b> Golfcross is a game that was invented in New Zealand. Players try to hit an oval golf ball into a net. Is this game played outside of New Zealand? Try searching for [golfcross] with Translated foreign pages and find out! Try clicking on different languages from among the 40+ available and see what you find.</p><p>If you are not interested in golfcross, search for a topic of personal interest to you and examine perspectives in other languages. Examples may be sports, keeping healthy, or travel. Share what you find in the <a href="LINK_TO_COURSE_FORUM" target="_blank">forum</a></p>',

];

