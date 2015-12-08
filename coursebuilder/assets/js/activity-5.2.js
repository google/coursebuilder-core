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

  '<table border="2"><tr><td><b>Search Tips:</b><p><ul><li>Verify the credibility of information you find on the web.<li>Avoid confirmation bias when conducting searches.<li> To verify the <b>source</b> of a piece of information, use the precise information you have.<li>To confirm a <b>fact</b>, use a generic description for what you seek.<li> Example: [average length octopus] will give you information about how long an octopus is. [18 inch long octopus] will give you sources with examples of octopuses of that length.</ul></tr></td></table>',

  '<p><b>1.</b> In Unit 1 Lesson 6, Dan mentioned that 90% of people don’t know about Control-F. Which of these queries is the most efficient way to help you confirm or refute that fact?</p>',

  { questionType: 'multiple choice',
    choices: [['[90 percent know Control-F]', false, 'Try again. What is the best way to confirm a fact? Are you using a generic description for what you seek?'],
              ['[90 Control-F]', false, 'Try again. What is the best way to confirm a fact? Are you using a generic description for what you seek?'],
              ['[know Control-F]', true, 'Correct! This is the most efficient way to verify the fact. You are using a generic description of what you seek.'],
              ['[number of people who know Control-F]', false, 'Try again. Is there a shorter way you could write this query?']]},

  '<p><b>2.</b> Which of the following searches would be most efficient to locate the original source of the data point that 90% of people don’t know Control-F?</p>',

  { questionType: 'multiple choice',
    choices: [['[90 percent know Control-F]', false, 'Try again. Is there a shorter way you could write this query?'],
              ['[90 Control-F]', true, 'Correct! When you need to know where a piece of data comes from, you should pick out the terms that you know will appear consistently in every source that talks about your subject. I know that the number 90 will appear in all reports on this study, and I know that Control-F will, as well. Beyond that, I cannot be certain of any terms appearing in all pages talking about the study. I can always add more words later if I get too many irrelevant results.'],
              ['[know Control-F]', false, 'Try again. What is the best way to identify a source? Are you using specific information that will find sources that give that specific fact?'],
              ['[number of people who know Control-F]', false, 'Try again. What is the best way to identify a source? Are you using specific information that will find sources that give that specific fact?']]},

  '<p><b>3.</b> You read an article that says:\n<p><font style="font-style:italic;">\nA recent study argued that college students should be paid for playing sports. It calculated that a typical basketball player is worth over $265,000 to his or her alma mater, while a college football player has a value of over $120,000. \n<\/font><p>\nOpen a new tab so you can search. What is the title of the original study on which this article is based?</p>',

  { questionType: 'freetext',
    correctAnswerRegex: /The Price of Poverty in Big Time College Sport?/i,
    correctAnswerOutput: 'Correct! From the passage provided, you can pull very specific search terms, such as [study basketball player $265,000], that will uniquely identify the source you want to find.',
    incorrectAnswerOutput: 'Try again. Look at the passage provided, and think about words or numbers that are very specific to the idea being communicated here. Try pulling those out to build a query.',
    showAnswerOutput: 'Our search expert says: The report is called \'The Price of Poverty in Big Time College Sport\'. You are trying to locate the source from which the information in the article came. To do so, you want to take very specific, identifiable pieces from the article and look for other pages that match. For example, a query such as [study basketball player $265,000], [college football player $120,000], or even [college player $265,000 $120,000] will uniquely identify the source you want to find.' },

];

