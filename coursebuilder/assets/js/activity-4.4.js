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

  '<table border="2"><tr><td><b>Search Tips:</b><p><ul><li>Limit results to sources published during a specific time period by clicking on Search Tools in the left panel, then selecting the appropriate time range.<li>Time filters are available in Web Search, Books, Images, News, Videos, Blogs, Discussions, and Patents.<li>This feature is not available on tablet browsers. </li></tr></td></table>',

  '<p>Try this activity to test your ability to restrict time of document publication.</p><p>In 1883, a volcano on the island of Krakatoa in Indonesia erupted. The dust from this massive volcano affected weather as far away as the United States. The volcano has recently become active again. Using the query [krakatoa volcano] and the time filter, identify the following pieces of information.</p>',

  '<p><b>1.</b> Which of these newspaper articles was published in 1883? Remember to search for [krakatoa volcano] and use time filtering.</p>',

  { questionType: 'multiple choice',
    choices: [['Volcano Mystery Solved', false, 'Try again. When you filter by time to only see articles in News from 1883, which of these headlines do you find?'],
              ['Venus has Volcanic Character', false, 'Try again. When you filter by time to only see articles in News from 1883, which of these headlines do you find?'],
              ['The Volcano Heard Around the World', false, 'Try again. When you filter by time to only see articles in News from 1883, which of these headlines do you find?'],
              ['Java\'s Canopy of Fire: A Volcano’s First Effort', true, 'Correct! Searching in News for [krakatoa volcano] allows you access to the custom time filter, where you can limit yourself to searching within newspaper articles from 1883.']]},

  '<p><b>2.</b> Which of these books was published on the Krakatoa volcano during the 1880s?</p>',

  { questionType: 'multiple choice',
    choices: [['How Volcanoes Work - Krakatau, Indonesia', false, 'Try again. Did you search for [krakatoa volcano], then filter by Books and time?'],
              ['Krakatoa: The Day The World Exploded: August 27, 1883', false, 'Try again. Did you search for [krakatoa volcano], then filter by Books and time?'],
              ['The Eruption of Krakatoa: And Subsequent Phenomena', true, 'Correct! Books has a time filter in the left panel that allows you to narrow your results to only works published in 1883. Among those results this report from the Royal Society of Great Britain.'],
              ['Surviving Yellowstone’s Super Volcano', false, 'Try again. Did you search for [krakatoa volcano], then filter by Books and time?']]},

  '<p><b>3.</b> What has been posted to the web about Krakatoa in the past week? Try it out before proceeding to the next lesson.</p>',

];

