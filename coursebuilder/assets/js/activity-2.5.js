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

  '<table border="2"><tr><td> <b>Search Tips:</b><p> <ul><li>In the left panel of the search results page, you can filter results by different categories.<li>These categories include blogs, discussions, recipes, patents, books, 3D models, scholarly sources, and legal documents.<li>The left panel does not appear on tablet computers (iPads and Android devices). </tr></td></table>',

  'In the video, Dan explored results in different media for the word [cats]. What do you love? Compare the information you find by searching for a topic of your choice and clicking on all the different media options. Share your story in the <a href="LINK_TO_COURSE_FORUM" target="_blank">forum</a>.',

];
