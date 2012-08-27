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

  '<table border="2"><tr><td><b>Search Tips:</b><p> <ul><li>When you do certain queries, Google presents information about these topics directly on the search results page.<li>You can distinguish the information in these panels from advertisements because advertisements are labeled as Ads. Also, when these panels appear, they are always the top box on the right-hand side.<li>Topics for which information panels appear include, but are not limited to, animals, famous people, landmarks, countries, movies, books, works of art, sports teams, and chemical elements.</ul> </tr></td></table><br>',

  'Have you ever played the <a href="http://en.wikipedia.org/wiki/Six_degrees_of_separation#Kevin_Bacon_game" target="_blank">"Six Degrees of Separation"</a> game, where you try to get from one celebrity to another via co-stars in movies they have in common? Clicking only in the information panels on the right side of the screen, our search expert got from Mona Lisa to the Golden Gate Bridge in seven clicks. That is, she entered the query [Mona Lisa], clicked on something in the panel on the right side of the screen, then clicked on something else in the resulting screen, and so forth, and finally ended up at a page about the Golden Gate Bridge. How did she do it? Can you do it with fewer clicks? <p>Find your own "six degrees" chain using the panels on the right. Share your story in the <a href="LINK_TO_COURSE_FORUM" target="_blank">forum</a>.',

];
