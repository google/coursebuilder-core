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

  '<table border="1"><tr><td><b>Search Tips:</b><p><ul><li>In the last video you learned how to select effective keywords. Remember to think about the words you think will be in your desired results page.<p> <li>Determine the most important words in your search as well as potential synonyms.</ul><p> </tr></td></table>',

  'You received this letter from a friend. <p><font style="font-style:italic;">Hi, I am a chef and a food blogger.  Recently, I wanted to write about this really yummy French sandwich with tuna and peppers and anchovies and stuff called a Pom Mignon, or something like that. For the life of me, I don’t know precisely what it is called. I spent half an hour last night typing every possible spelling I could think of into Google, but could not find it. What do I do now? <p>Thank you,<br>L.</font><p>Given what you know about this problem, what query would you use to solve it?<p>',

  { questionType: 'freetext',
    showAnswerPrompt: 'Compare with Expert',
    showAnswerOutput: 'Our expert says: Different people have different styles for searching for information. Here is how I identified the sandwich--though it is not the only way to arrive at an answer.\n\nI searched for [french sandwich tuna peppers anchovies]. \n\nRemember how Dan talked about thinking about what you want to find? What words will be on the kind of page you want to appear? \n\nSo, ask yourself what kind of page is likely to:\n\n1. Give the name of this sandwich?\n2. Be a common resource on the web?\n3. Make use of the other information you have about the sandwich--since the name was obviously a dead-end?\n\nI thought of a recipe! A recipe lists all of the ingredients. In this case, the chef knew several of the ingredients, but did not connect the fact that she knew them to the idea that she could use them in a basic web search.\n\nScroll down to continue. ',
    outputHeight: '300px' },

  '<br><br>Can you find the name of the sandwich in the results below?<br>',

  '<br><img src="assets/img/Image10.1.png"<p>',

  '<br>What\'s the name of the sandwich?<br>',

  { questionType: 'freetext',
    showAnswerPrompt: 'Check Answer',
    showAnswerOutput: 'Pan Bagnat!'},

];
