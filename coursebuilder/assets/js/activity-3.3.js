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

  '<table border="2"><tr><td> <b>Search Tips:</b><p> <ul><li>Use the minus sign (-) to eliminate irrelevant results.<li>There must be a space before the minus sign.<li>There must not be a space between the minus sign and the word you want to eliminate.<li>A plus sign (+) does not mean “and” nor does it force inclusion of a word. Google can search for certain plus signs after a word (for example, C++ or Google+). A plus sign before a search term, used as an operator, looks for a Google+ Page by that name.</ul> </tr></td></table>',

  '<p><b>1.</b> You are helping a neighbor’s child find information on penguins. Since it is hockey season, when you simply search for [penguins] you get many pages on the Pittsburgh Penguins mixed in with results about the bird. Which of these is a way you can narrow your results to focus on the animal?</p>',

  { questionType: 'multiple choice',
    choices: [['[penguins NOT pittsburgh]', false, 'Please try again. Remember that Google uses a minus sign (-) to eliminate results. You can go to Google.com and try the search [penguins NOT pittsburgh] and look carefully at your results. You will notice that the word "not" appears throughout your results in boldface. When a word appears in boldface in search results, it means that Google has used it as a search term rather than an operator.'],
              ['[penguins -pittsburgh]', true, 'Correct! When you search for -pittsburgh, without any spaces, you will easily eliminate pages with the word Pittsburgh on them.'],
              ['[penguins without pittsburgh]', false, 'Please try again. Remember that Google uses a minus sign (-) to eliminate results. You can go to Google.com and try the search [penguins without pittsburgh] and look carefully at your results. You will notice that the word "without" appears throughout your results in boldface. When a word appears in boldface in search results, it means that Google has used it as a search term rather than an operator. You may also notice the term "not", because Google identifies the word "not" as a synonym for "without" in this instance.'],
              ['[penguins - pittsburgh]', false, 'Please try again. Remember that Google understands the minus sign operator when there is no space between the minus sign and the word you want to eliminate, such as -chicago.']]},

  '<p><b>2.</b> You want pages that talk about Jane Austen books. When you search for [jane austen books] you get a lot of pages selling books by Jane Austen mixed into the results, but you don’t want to buy anything right now. Luckily, you notice that pages selling stuff almost always have the word price on them, so you decide to try rewriting the query so that it eliminates the word price from all your results. What would that query look like?</p>',

  { questionType: 'freetext',
    correctAnswerRegex: /jane austen (book|books) \-price/i,
    correctAnswerOutput: 'Correct! When you search for -price, without any spaces, you will easily eliminate pages with the word price on them. In fact, the word buy also appears frequently on pages selling things, so you can make the search even more effective this way: [jane austen books -price -buy].',
    incorrectAnswerOutput: 'Try this question again. How can you remove price information from your query?',
    showAnswerOutput: 'Our search expert says: I would use [jane austen books -price]. When you search for -price, without any spaces, you will easily eliminate pages with the word price on them. In fact, the word buy also appears frequently on pages selling things, so you can make the search even more effective this way: [jane austen books -price -buy].' },

  '<p><b>3.</b> Can you think of a time that the minus sign operator would help you find what you need faster? Try it out before proceeding to the next lesson and share your story in the <a href="LINK_TO_COURSE_FORUM" target="_blank">forum</a>.</p>',

];
