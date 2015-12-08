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

  '<table border="2"><tr><td><b>Search Tips:</b><p><ul><li>Hovering over the page preview tool (>> icon to the right of search results) allows you to preview results pages.</li><li>There are three main parts of a search engine result: the page title (in blue), the web address (in green), and the snippet/abstract (in black). The snippet contains the text from the page that appears around the terms you search for.</li><li>Links within the search engine results go directly to subpages of the site.</li><li>Use the site: operator to restrict results to a domain, website, or directory.</li></ul></tr></td></table>',

  // Note: the entire question should be encapsulated into one string.

  // This is a custom activity type where the user clicks on an image map, and feedback is displayed in a textarea:
  '<form name="quiz"><b>1.</b> Click on the following in the result block below: <ol style="list-style-type:lower-alpha"><li>web address</li><li>web page title</li><li>snippet</li></ol><img src="assets/img/Image2.3.1.png" usemap="#Image2.3" border="0"><map name="Image2.3">\n<area shape="rect" coords="15,14,605,36" onClick="check24(1)" ><area shape="rect" coords="15,37,545,56" onClick="check24(2)"><area shape="rect" coords="14,56,665,100" onClick="check24(3)" ></map><p><p><textarea style="width: 600px; height: 30px;" readonly="true" name="output"></textarea></form>',

  '<p><b>2.</b> Do you think the page associated with the result above would contain the sentence "Quality standards for pharmaceuticals have historically been an area of focus for USP"?</p>',

  { questionType: 'multiple choice',
    choices: [['Yes', false, 'Incorrect. Note that the ellipsis (...) indicate that you are seeing phrases from two different parts of the webpage. The information in between may change the meaning of what you see in the snippet.'],
              ['No', true, 'Correct! Note that the ellipsis (...) indicate that you are seeing phrases from two different parts of the webpage. The information in between may change the meaning of what you see in the snippet.']] },

];


// Note that the following code (that is not part of the definition of the
// 'activity' variable) needs to be surrounded with the commented tags
// '// <gcb-no-verify>' and '// </gcb-no-verify>', so that the verifier script
// in tools/verify.py does not treat the code as invalid.


//<gcb-no-verify>

// JavaScript code to check which area of the image the user clicked on
// and display the appropriate message in the output textarea:
function check24(incoming) {
  if (incoming == 1) {
    document.quiz.output.value = 'You have clicked on the web page title, which is always the first line of text in a result.';
  } else if (incoming == 2) {
    document.quiz.output.value = 'You have clicked on the web address, which is always the green text in a result block.';
  } else {
    document.quiz.output.value = 'You have found the snippet, which is the black text that shows where your search terms appear on the page.';
  }
}

//</gcb-no-verify>
