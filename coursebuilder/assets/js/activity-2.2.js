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

  '<table border="2"><tr><td> <b>Search Tips:</b><p> <ul><li>Sometimes search results offer information that suggests a better or additional search.<li>Use [define] in the search box to identify the meaning of words.<li>Click on Search Tools in the left panel, then Dictionary to define words that do not appear in traditional dictionaries.</ul> </tr></td></table>',

  '<b>1.</b> You are a cosmetologist and business owner, and have been asked by a few clients if you are going to offer those fish that clean people\'s feet. To learn more, you search for [fish clean feet]. <p><a href="assets/img/Image2.2.1.png" target="_blank"><img src="assets/img/Image2.2.1.png" width="618" height="504" alt="search results for [fish clean feet]" title="search results for [fish clean feet]"></a><p> Do these results look helpful for making business decisions?',

  { questionType: 'multiple choice',
    choices: [['Yes', false, 'Your answer is incorrect. Please try again.'],
              ['No', true, 'Your answer is correct! These results appear to be casual information; the kind that is shared friend-to-friend. For business decisions, you probably should consider more professional or formal sources of information about this trend.']]},

  '<p><b>2.</b> You modify your search to give you more precise information. What are some more business-oriented terms suggested by these results?</p>',

  { questionType: 'freetext',
    showAnswerPrompt: 'Show Answer',
    showAnswerOutput: 'Possible search terms based on the results above could be [fish pedicure], [doctor fish], or [fish spa].' },

  '<p><b>3.</b> While you are researching more about fish pedicures and doctor fish (which go by the scientific name of Garra rufa), you discover that the Centers for Disease Control says "Garra rufa are native to the Middle East, where they have been used as a medical treatment for individuals with skin diseases, like psoriasis." You want to know what psoriasis is. What would your search look like?</p>',

  { questionType: 'freetext',
    showAnswerPrompt: 'Show Answer',
    showAnswerOutput: 'Any of the following would work: [define psoriasis], [define:psoriasis], [define: psoriasis].' },

];
