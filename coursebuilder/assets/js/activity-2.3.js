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

  '<table border="2"><tr><td> <b>Search Tips:</b><p> <ul><li>Use image search when it appears in search results, and use related image search to refine results.<li>Refine results by using different media types like videos and news; these filters appear in the left side of the search results page.<li>Google’s left menu does not appear on tablet computers (iPads, Android tablets).</ul> </tr></td></table><br>',

  '<b>1.</b> Your friend was telling you about this new term for a kind of urban protest graffiti called "Yarnbombing". Despite the name, the friend said it is a completely light-hearted, non-violent art form, but you do not understand what it is. <p>What is the most efficient way to find recent News articles about yarnbombing?',

  { questionType: 'multiple choice',
    choices: [['[yarnbombing news article]', false, 'Try again. This is a risky approach, since many news articles do not call themselves \'news articles\' on the page. Those search terms may make it harder to find good content.'],
              ['[yarnbombing] then click News in the left menu', true, 'Correct! Using a collection of a specific type of media, like News, can help you get to the best pages faster.'],
              ['[i would like to find news articles about yarnbombing]', false, 'Try again. We want to avoid including a lot of extra, confusing words into a query.'],
              ['[what are some recent publications about yarnbombing]', false, 'Try again. Stating what you want in this way, introduces a lot of extra words into a query.']]},

  '<br><br><br><b>2.</b> You would like to try yarnbombing, but you need some advice about how to do it well. Unfortunately, when you try following instructions you read online, it never quite works right. You want to see someone doing it, and in some detail--at least a good five minutes of instructions. What media do you use?',

  { questionType: 'freetext',
    correctAnswerRegex: /video?/i,
    correctAnswerOutput: 'Correct! Searching in Google Videos is a great way to look across YouTube and other sites with videos. If you look at the links on the left-hand side of the Google Videos Results page, you will see that you can specify how long the video should be.',
    incorrectAnswerOutput: 'Some people find videos very helpful to see how to carry out tasks. Look at the diferent media offered in the left-hand column. Which one would help you find videos?',
    showAnswerOutput: 'You can use the Videos collection to search exclusively for videos on a topic without getting other kinds of results.' },

  '<br><br><br><b>3.</b> Now that you’ve read an article or two about yarnbombing, you want to see some pictures of it. Go to Google Images and look up [yarnbombing].',

];
