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

  '<table border="1"><tr><td><b>Search Tips:</b><p>In the last video, you learned how to quickly find text on a page:</p><ul><li>Windows computers: press the control and F keys at the same time. <p><li>Apple computers: press the command and F keys at the same time. <p><li>Android tablets: in a browser window, touch the menu button in the top right of the screen, then select "find on page". <p><li>Safari on iPad tablets: click the cursor in the search box in the upper right corner of the screen. Directly above the keyboard, a "find on page" box will open. </tr></td></table><p>For the following questions, go to the <a href="http://earthquake.usgs.gov/earthquakes/world/historical.php/" target="_blank"> US Geological Survey’s list of Historic World Earthquakes</a>.</p>',

  { questionType: 'multiple choice group',
    questionsList: [ {questionHTML: '<b>1.</b> In the United States, the state of California is known for its earthquakes. Have there been earthquakes in Iowa?',
                      choices: ['Yes', 'No'],
                      correctIndex: 0},

                     {questionHTML: '<b>2.</b> Has there ever been an earthquake in Maine?',
                      choices: ['Yes', 'No'],
                      correctIndex: 0},

                     {questionHTML: '<b>3.</b> Which state (Iowa or Maine) had an earthquake more recently?',
                      choices: ['Iowa', 'Maine'],
                      correctIndex: 1}
                   ],
    allCorrectOutput: 'Hopefully you used Control-F to find the information quickly.',
    someIncorrectOutput: 'Remember, you can use Control-F to find information like this more quickly. Please try again.'},

  '<p><b>4.</b> When was the last historic earthquake in your area? Share your answer in the <a href="LINK_TO_COURSE_FORUM" target="_blank">forum</a>.</p>',

];
