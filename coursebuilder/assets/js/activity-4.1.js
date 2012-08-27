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

  '<table border="2"><tr><td> <b>Search Tips:</b><p> <ul><li>You can identify an image using Google search by using the "Search by Image" feature.<li>Visit images.google.com, or any Images results page, and click the camera icon in the search box. Enter an image URL for an image hosted on the web or upload an image from your computer.<li>  You can also Learn more about Search by Image <a href="http://support.google.com/images/bin/answer.py?hl=en&p=searchbyimagepage&answer=1325808" target="_blank">here</a>.<li>Search by Image is supported on these browsers: Chrome, Firefox 3.0+, Internet Explorer 8+, and Safari 5.0+. <li> To Search by Image on an Android device, use an app like Google Goggles to take a photo of an object or image. <li> Search by Image is not currently supported on tablet browsers.</ul> </tr></td></table>',

  '<p>While sorting through some trinkets at a garage sale, you find the image below. There is a note scrawled on the back that says, "ancestor of manga". Since you are interested in manga, you decide you would like to see the original.</p><img src="http://upload.wikimedia.org/wikipedia/commons/f/fa/Chouju_sumo2.jpg" border="0" alt="ancestor of manga" title="ancestor of manga"><p> In what temple is the original located?</p>',

  { questionType: 'freetext',
    correctAnswerRegex: /Kozanji|Kozan-ji|Kosanji|Kosan-ji/i,
    correctAnswerOutput: 'Correct--when you drag the image into the Google Images search box, Google automatically identifies it, and points you to several pages with this information.',
    incorrectAnswerOutput: 'Our search expert says that you can use Search by Image to answer this question. The temple is called Kozanji (which is spelled a variety of ways in English).',
    showAnswerOutput: 'Our search expert says that you can use Search by Image to answer this question. The temple is called Kozanji (which is spelled a variety of ways in English).\n\n(Hint: you can drag and drop the image, or, on any webpage, right-click an image and select the option to copy it. In most browsers, this option\'s name starts with "Copy image," except Internet Explorer for which you\'ll select "Properties" and then copy the URL that\'s then displayed.)',
    outputHeight: '90px' },

];
