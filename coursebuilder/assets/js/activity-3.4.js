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
  '<table border="2"><tr><td> <b>Search Tips:</b><p> <ul><li>Use quotes to search for a phrase.</li><li>Quotes glue words together; there can be additional words before or after the phrase, but the phrase will always stay together in the results.</li><li>Use OR to include more than one way of expressing an idea.</li><li>If an idea on one side of the OR is more than one word, it needs quotes around it (for example [handkerchief OR "facial tissue"])</li></ul> </tr></td></table>',

  '<p><b>1.</b> Your friend has been complaining about her ex a lot; he is still hanging around even though they broke up. This reminded you of a line from a poem: Like black tape he is stuck to me. You search for it and see the results below. <p><img src="assets/img/Image3.4.2.png"><br><br>How could you modify the query to find the poem?</p>',

  { questionType: 'multiple choice',
    choices: [['[“like black tape he is stuck to me”]', true, 'Correct! Putting quotes around a set of words keeps them together in a phrase.'],
              ['[like black tape he is stuck to me poem]', false, 'Please try again. Use an operator to signal to Google that the words in the query need to stay together as a phrase. Adding an extra word will not help.'],
              ['[/like black tape he is stuck to me/]', false, 'Please try again. Use an operator to signal to Google that the words in the query need to stay together as a phrase.'],
              ['[(like black tape he is stuck to me)]', false, 'Please try again. Use an operator to signal to Google that the words in the query need to stay together as a phrase. Google ignores parentheses.']]},

  '<p><b>2.</b> Now you are looking for another poem, one with the line Don’t ask Joe what it is to him. Once again, the words do not stay in a phrase, but get scattered all over the page. What would your query look like if you were going to solve that problem?</p>',

  { questionType: 'freetext',
    correctAnswerRegex: /\"don’t ask joe what it is to him\"/i,
    correctAnswerOutput: 'Correct! You can use double quotes around the phrase to specify that all the words need to stay together.',
    incorrectAnswerOutput: 'Think about which operator you can use to keep the words together as a phrase.',
    showAnswerOutput: 'Our search expert says: I would use ["don’t ask joe what it is to him"]. You can use double quotes around the phrase to specify that all the words need to stay together. Think of words within quotation marks holding hands.' },

  '<p><b>3.</b> You would like to find information on green marketing, the practice of portraying companies as being environmentally responsible. You look at your initial search results, and see that "Greenwashing" is a term used to describe this idea. But there are also synonyms: greenscamming and greenspeak. What search would you run to find pages using any of those three synonyms?</p>',

  { questionType: 'multiple choice',
    choices: [['[greenwashing greenscamming greenspeak]', false, 'Please try again. You need to use an operator to tell Google that you only need one word from this set of options. Just typing in all the words like this will only find pages containing all three words, and miss pages that use just one of them.'],
              ['[greenwashing, greenscamming, greenspeak]', false, 'Please try again. Google ignores commas.'],
              ['[greenwashing or greenscamming or greenspeak]', false, 'Please try again. Google only interprets OR as an operator when both the O and the R are written in capital letters. When it is written in lowercase (or) the word is interpreted as a search term. Here, Google would prefer pages containing all of the following words: greenwashing, or, greanscamming, and greenspeak.'],
              ['[greenwashing OR greenscamming OR greenspeak]', true, 'Correct! You can use OR (all in capital letters) between two words to have Google find pages using one word OR the other.']]},

  '<p><b>4.</b> You are getting ready to go out to dinner, and you cannot decide between eating Thai food and Vietnamese food. What query could you use to find both Thai and Vietnamese restaurant choices in your area?</p>',

  { questionType: 'freetext',
    correctAnswerRegex: /.+ \O\R .+/,
    correctAnswerOutput: 'Correct! You can use OR between two words to find pages including one or the other.',
    incorrectAnswerOutput: 'Think about which operator you can use to express that you want one word or the other.',
    showAnswerOutput: 'Our search expert says: I would use  [restaurant thai OR vietnamese].  You can use OR between two words to find pages including one or the other.' },

  '<p><b>5.</b> Truck owners are insured when they are on a job for a company, but need to carry their own insurance policy for when their truck is empty. You would like to get an idea of the cost of this type of insurance, which is sometimes called, non-trucking liability, bobtail, or deadhead coverage. What search would you use to get information on the cost of this insurance on pages that use any of these <b>three</b> terms? In other words, what search would you do to find pages using any of three synonyms?</p>',

  { questionType: 'freetext',
    correctAnswerRegex: /cost insurance .+ \O\R .+ \O\R .+/,
    correctAnswerOutput: 'Correct! You can use OR (all in capital letters) between two words to have Google find pages using one word OR the other. You can use quotes (“  “) around two-word phrases to fine one phrase OR the other.',
    incorrectAnswerOutput: 'Consider what operator you can use between two words if you want Google to find one or the other of them. Also, remember that you need to tell Google to consider multi-word terms, like deadhead coverage as a single phrase.',
    showAnswerOutput: 'Our search expert says: I would use  [cost insurance "non-trucking liability" OR bobtail OR "deadhead coverage"].  You can use OR (all in capital letters) between two words to have Google find pages using one word OR the other. You can use quotes ("  ") around two-word phrases to find one phrase OR the other.' },

];
