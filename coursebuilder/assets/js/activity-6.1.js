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

  '<table border="2"><tr><td><b>Search Tips:</b><p><ul><li>Combine operators for stronger searches.<li>Operators can be placed anywhere in the query without affecting the results. For example: [black cats site:com] is equivalent to [site:com black cats].</ul></tr></td></table>',

  '<p><b>1.</b> Which of these searches shows an <b>effective</b> use of multiple operators?</p>',

  { questionType: 'multiple choice',
    choices: [['[household spending site:org -site:edu]', false, 'Please try again. You will only see results in .org domains, so you do not also have to eliminate .edu sites.'],
              ['[site:edu site:org household spending]', false, 'Please try again. By searching for [site:edu site:org] you are telling Google to limit results to only .edu sites, and also to limit results to only .org sites. Sites can only be in one or the other. If you wanted to find sites in either .edu or .org domains, you could write this query as [site:edu OR site:org].'],
              ['[site:census.gov filetype:pdf household spending]', true, 'Correct! You can combine site: and filetype: for very targeted results when necessary.'],
              ['[household spending site:edu OR org]', false, 'Please try again. When you use an operator, you cannot combine different terms using OR. The query [site:edu OR org] is not the same as [site:edu OR site:org].']]},

  '<p><b>2.</b> You work for an environmental services company. NASA’s website indicates that the agency is a model of sustainability. You want to get a better notion of what others think about their environmental management. You decide to look at what other government (.gov) or military (.mil) organizations have to say about NASA’s programs. You do not want to see results from NASA.gov itself.</p>',

  '<p>You know that you want the following elements in your search: [nasa environmental management OR policy]; .mil sites; .gov sites; but NOT anything from NASA.gov. Go to a new tab and search for this information in Google.</p>',

  '<p>Did your search match any of the following? Which will work best?</p>',

  { questionType: 'multiple choice',
    choices: [['[nasa environmental management OR policy site:gov OR site:mil]', false, 'Please try again. What do you need to do to eliminate a website you don’t want from your results?'],
              ['[nasa environmental management OR policy site:gov OR site:mil -site:nasa.gov]', true, 'Correct! You have to cover both the .gov and the .mil domain. You do this with site: searches that have ORs in between them. To get rid of results from the NASA site, you again do a site: search, this time with a minus sign in front of it.'],
              ['[nasa environmental management OR policy site:gov OR site:mil -nasa]', false, 'Please try again. Consider what happens if you just tell Google [-nasa]. What will that eliminate?'],
              ['[nasa environmental management policy site:gov site:mil -site:nasa.gov]', false, 'Please try again. Right now, how are you asking Google to behave towards synonyms or similar concepts? Will Google be able to carry out this query?']]},

];

