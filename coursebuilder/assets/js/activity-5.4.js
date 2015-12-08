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

  '<table border="2"><tr><td><b>Search Tips:</b><p><ul><li>Use a query containing WHOIS to identify the owner of a particular website.<li> If you see a second company listed as a contact on the WHOIS page, then a relationship exists between the two companies. You can then do another search to determine that relationship.<li>Example: [whois] finds WHOIS registries you can use. Find the search box for the registry, and enter [zagat.com]. See that Google is the registrant. Search for [google zagat], which leads to the information that Google acquired Zagat.<li>The US Chamber of Commerce operates the WHOIS search available at http://www.internic.net/whois.html; alternative WHOIS registries also exist.<li> If you don’t know a company\'s website, you can search for the company’s name in Google and locate the web address.</tr></td></table>',

  '<p>WHOIS lookups are not something we anticipate you’ll use often, but they can be helpful.<p>Different WHOIS directories post different information, and they can be challenging to read, so use this question to practice.<p>Open a new window and use the Web to answer this question. For this exercise, go to <a href="http://www.internic.net/whois.html" target="_blank">http://www.internic.net/whois.html</a> or a different directory of your choice.</p>',

  '<p><b>1.</b> What do you see listed as the name server (sometimes called the domain server) for Splenda.com?</p>',

  { questionType: 'multiple choice',
    choices: [['bnb.com', false, 'Try again. You are looking for the name server or the domain server for splenda.com.'],
              ['jnj.com', true, 'Correct! jnj.com is listed as the name server for splenda.com, which means that jnj.com owns splenda.com.'],
              ['whois.networksolutions.com', false, 'Try again. You found the domain registry for Splenda.com, but you are looking for the name server.'],
              ['splenda.com', false, 'Try again. You are looking for the name server or the domain server for splenda.com.']]},

  // in this custom question type, the user writes a reply and then clicks on the output textarea to see feedback:
  '<p><b>2.</b>  Based on the information you found in question one, what company owns Splenda?<br><input type="text" class="alphanumericOnly" style="border:1px solid black;" id="txtbox1" onBlur="show54_2()"></p><p><font color="gray">Click here to see feedback</font><br><textarea style="width: 600px; height: 15px;" readonly="true"  id="output2"></textarea></p>',

];


// Note that the following code (that is not part of the definition of the
// 'activity' variable) needs to be surrounded with the commented tags
// '// <gcb-no-verify>' and '// </gcb-no-verify>', so that the verifier script
// in tools/verify.py does not treat the code as invalid.


//<gcb-no-verify>

// JavaScript support code for displaying text into the proper output textarea (uses jQuery)
function show54_2() {
  $('#output2').val('If you do a search on jnj.com, you will find that jnj.com is Johnson & Johnson.');
}

//</gcb-no-verify>
