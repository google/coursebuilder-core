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

  '<table border="2"><tr><td> <b>Search Tips:</b><p> <ul><li>In the previous video, you learned about the filetype operator. Typing filetype, followed by a colon (:) and the appropriate extension, will return files of the extension you specify. <li>There should not be a space between filetype, the colon, and the extension: [filetype:txt]<li>You do not need to put a period before the extension; you can just use the three or four-letter code (swf, xlsx, jpg, gif, etc.).<li><a href="http://support.google.com/webmasters/bin/answer.py?hl=en&answer=35287" target="_blank">Here</a> is a list of file types Google indexes. </ul><p> </tr></td></table>',

  '<p><b>1.</b> You want to find a sound file that will teach you Morse Code for "I love you". Your friend told you that Wikimedia has all these audio files of people saying things in different languages, in a format called .OGG. Which of the following queries can you use to most easily find the file you want?</p>',

  { questionType: 'multiple choice',
    choices: [['[i love you morse code ogg:filetype]', false, 'Please try again. Remember that Google understands the operator filetype: when it is FOLLOWED BY the kind of file you want, such as filetype:ppt. '],
              ['[i love you file morse code type:ogg]', false, 'Please try again. Remember that Google understands the operator filetype: when it is written as all one word.'],
              ['[i love you morse code filetype:ogg]', true, 'Correct! When you search for filetype:ogg, without any spaces, you will find pages of your specified type very quickly and easily.'],
              ['[i love you morse code filetype: ogg]', false, 'Please try again. Remember that Google understands the operator when you enter filetype:ogg with no space after the colon (:). When you put a space after the colon (as in filetype: ogg), Google returns pages with the words filetype and ogg.'],
              ['All of the above', false, 'Please try again. Only one of these works consistently to find a particular type of file. Look carefully and see which one is correct.']]},

  '<p><b>2.</b> Your boss is going to Japan, where he will be taken to see a Kabuki play. He asks you for a bit of background on Kabuki. You know that he prefers to read on paper. What would your search look like to find a PDF to print for him?</p>',

  { questionType: 'freetext',
    correctAnswerRegex: /filetype:pdf?/i,
    correctAnswerOutput: 'Correct! You can use the filetype: operator to specify when you want a particular kind of file, like a pdf, xls, or ppt.',
    incorrectAnswerOutput: 'Try this question again. Think about which operator you can use to specify when you want a particular kind of file, like a pdf, xls, or ppt. And watch where you put spaces!',
    showAnswerOutput: 'Our search expert says: I would use [kabuki filetype:pdf]. You can use the filetype: operator to specify when you want a particular kind of file, like a pdf, xls, or ppt.' },

    '<p><b>3.</b> Can you think of a time that filetype: might have helped you find what you need faster? Try it out before proceeding to the next lesson.</p>',

];
