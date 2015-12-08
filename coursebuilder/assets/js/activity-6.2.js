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

  '<table border="2"><tr><td><b>Search Tips:</b><p><ul><li>Combine methods and approaches to find information efficiently.</li><li>Use tools that are not traditionally used for research, like Maps and Street View.<li>On tablets, it’s best to use the Google Maps application instead of looking at streetview in the browser.</ul></tr></td></table>',

  'You are finally getting that long-awaited dream trip to Paris. You want to stay at the MERCURE PARIS MONTMARTRE SACRE COEUR in Paris at 3 Rue Caulaincourt 75018 France. Most people say it is a lovely neighborhood, but you want to see what it looks like--especially the walk from the hotel to the Place de Clichy metro station just over a block away.<br><br>Take a stroll from your hotel to the subway station.<br><br>As you go, be sure to notice some of the restaurants available just across the street from your hotel.<br><br>What kind of restaurant is there between the sandwich shop and the souvenir store just across the street--that one with the black, white, and red sign?<br><br>',

  { questionType: 'freetext',
    correctAnswerRegex: /japanese|sushi/i,
    correctAnswerOutput: 'Correct! Using Street View in Google Maps allows you to check out a neighborhood you want to visit and make sure it meets your needs.',
    incorrectAnswerOutput: 'Try again. Consider the special features in Google Maps that allow you to take a stroll around a neighborhood before visiting it.',
    showAnswerOutput: 'Our search expert says: I found a Japanese sushi restaurant using Street View in Google Maps. It allows you to check out a neighborhood you want to visit and make sure it meets your needs.' },

];

