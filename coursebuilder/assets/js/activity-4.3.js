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

  '<table border="2"><tr><td> <b>Search Tips:</b><p> <ul><li>Enter any math equation into the search box, and Google will calculate your answer.<li>These search features are available on cell phone, iPad, or anywhere Google is available (like on your phone while you are cooking in the kitchen).</li> </tr></td></table> Try this activity to practice doing conversions in Google search.<p>',

  '<b>1.</b> What is 41 degrees Celsius in Fahrenheit?',

  { questionType: 'freetext',
    correctAnswerRegex: /105.8/,
    correctAnswerOutput: 'Correct! The query [41 c in f] will give you the conversion of Celsius to Fahrenheit.',
    incorrectAnswerOutput: 'Try a simple conversion, using a query similar to this one: [5.4 miles in km].',
    showAnswerOutput: 'It is 105.8 degrees. A query like [41 c in f] will give you the conversion of Celsius to Fahrenheit.' },

  '<br><br><b>2.</b> If you have 100 Rupiah, how much do you have in Yen?',

  { questionType: 'freetext',
    showAnswerPrompt: 'Show Answer',
    showAnswerOutput: 'Using the query [100 rupiah in yen] will find you today\'s approximate rate of exchange.' },

  '<br><br><b>3.</b> You have a recipe for making one quart of barbecue sauce and you want to make ten quarts instead. If the original recipe calls for 4 tablespoons of sugar, how many cups of sugar should you use?',

  { questionType: 'freetext',
    correctAnswerRegex: /2.5?/,
    correctAnswerOutput: 'Correct! You can either ask Google to directly calculate [4 tablespoons * 10 in cups], or you can first ask for [4 tablespoons * 10 ] and then convert [591.470591 milliliters in cups].',
    incorrectAnswerOutput: 'What would this math problem look like? You need to multiply the amount of sugar by the number of recipes you are making, and then convert that amount into cups.',
    showAnswerOutput: 'It is 2.5 cups of sugar. You can either ask Google to directly calculate [4 tablespoons * 10 in cups], or you can first ask for [4 tablespoons * 10 ] and then convert [591.470591 milliliters in cups].' },

];
