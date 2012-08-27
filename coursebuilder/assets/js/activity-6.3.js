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

  '<table border="1"><tr><td><p><b> Visit each of the links below to explore ways to keep yourself updated on Google Search tools:</b></p><ul><li> Pick a blog to read to keep up-to-date:<ul><li><a href="http://googleblog.blogspot.com/" target="_blank"> Official Google Blog</a></li><li><a href="http://insidesearch.blogspot.com/" target="_blank"> Inside Search</a></li><li><a href="http://searchresearch1.blogspot.com/" target="_blank"> SearchResearch (by Dan Russell)</a></li></ul></li><li> Set up an <a href="http://www.google.com/alerts" target="_blank"> email alert</a> to notify you when there is a new feature.</li><li> Try out the <a href="http://agoogleaday.com" target="_blank"> AGoogleADay</a> game on Google+</li></ul></tr></td></table>'

];

