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

  '<table border="2"><tr><td><b>Search Tips:</b><p><ul><li>Verify the credibility of information you find on the web.<li>To check your findings, just do one more search.</ul></tr></td></table>',

  'Credibility--can you trust the information you find online? How can you find out whether information is accurate and true? There are a few ways to check credibility.<br><br>',

  '<p><b>1.</b> Take a moment to read <a href="http://webcache.googleusercontent.com/search?sugexp=chrome,mod=11&sourceid=chrome&ie=UTF-8&q=cache%3Awww.pcworld.com%2Fbusinesscenter%2Farticle%2F226912%2Fgoogle_date_range_filter_simplifies_search_results.html" target="_blank">Robert Strohmeyer\s post at PCWorld</a> about how he used Advanced Search to verify this quote: "I mourn the loss of thousands of precious lives, but I will not rejoice in the death of one, not even an enemy".</p>',
  '<p>Here are some other interesting online resources that examine the authenticity of quotes:</p>',
  '<ul><li><a href="http://webcache.googleusercontent.com/search?sugexp=chrome,mod=11&sourceid=chrome&ie=UTF-8&q=cache%3Awww.theatlantic.com%2Fnational%2Farchive%2F2011%2F05%2Fanatomy-of-a-fake-quotation%2F238257%2F" target="_blank">Anatomy of a Fake Quotation</a> by Megan McArdle of The Atlantic</li><li><a href="http://webcache.googleusercontent.com/search?sugexp=chrome,mod=11&sourceid=chrome&ie=UTF-8&q=cache%3Awww.monticello.org%2Fsite%2Fblog-and-community%2Fposts%2Fhow-to-spot-fake" target="_blank">How to Spot a Fake</a> by Anna Berkes, research librarian at Monticello</li><li><a href="http://webcache.googleusercontent.com/search?sugexp=chrome,mod=11&sourceid=chrome&ie=UTF-8&q=cache%3Aquoteinvestigator.com" target="_blank">QuoteInvestigator</a> by Garson O\'Toole</li></ul>',

  '<p><b>2.</b> Have you ever had a search result, where you doubted its truth?  What did you see that made you doubt it? Reflect on this before proceeding to the next lesson.</p>',

];

