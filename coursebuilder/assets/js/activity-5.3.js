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
//    asks for help.

var activity = [

  '<table border="2"><tr><td><b>Search Tips:</b><p><ul><li>Search appropriate sources that offer authoritative information for the type of information you are trying to find.</ul></tr></td></table>',

  '<p>Charles Darwin’s book, On the Origin of Species, introduced the idea of evolution. Open a new tab and go to the <a href="http://books.google.com/books?id=d9biAAAAMAAJ&dq=origin%20of%20species&pg=PA4#v=onepage&q&f=false" target="_blank">full-text version of the book</a>.</p>',

  '<p><b>1.</b> On what page does the word evolution appear?</p>',

  { questionType: 'freetext',
    correctAnswerRegex: /4|four/i,
    correctAnswerOutput: 'Correct! Using Google Books\' special \'find\' box in the left panel, typing in evolution and clicking on the \'Go\' button, you can see there is only one place the word evolution apprears in the text of the book.',
    incorrectAnswerOutput: 'Try again. Did you type evolution in the left search panel in Google Books?',
    showAnswerOutput: 'Using Google Books\' special \'find\' box in the left panel, typing in evolution and clicking on the \'Go\' button, you can see evolution appears on page 4.' },

  '<p><b>2.</b> Did Darwin, himself, use the word evolution in this book?</p>',

  { questionType: 'multiple choice',
    choices: [['Yes', false, 'Try again. Where in the book does this word appear?'],
              ['No', true, 'Correct! The word evolution appears in the editor’s note, which was not written by Charles Darwin.']]},

  '<p><b>3.</b> Lewis Carroll’s book, Alice’s Adventures in Wonderland, has many memorable characters, among them the Mad Hatter. We have discovered that the phrase “Mad Hatter” does not actually appear in the book, however. Can you think of another example of a book with a frequently-attributed phrase in which the phrase does not actually appear in the text of the book? Try it out before proceeding to the next lesson and share your story in the <a href="LINK_TO_COURSE_FORUM" target="_blank">forum</a>.</p>',

];

