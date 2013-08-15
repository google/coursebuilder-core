/*
 * Copyright 2013 Google Inc. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/*
 * Utils for full text search dashboard controls
 *
 * @author: emichael@google.com (Ellis Michael)
 */

// requires jQuery (>= 1.7.2)


function indexDocs(event) {
  var token = $('#gcb-index-course > input[name=xsrf_token]').attr('value');
  $.post('dashboard?action=index_course',
         { xsrf_token: token },
         function(data) {
           var response = JSON.parse(data.replace(")]}'\n", ''));
           cbShowMsg(response.message);
         }, 'text'); // The JSON parser doesn't accept the XSSI_PREFIX
  event.preventDefault();
}

function clearIndex(event) {
  var token = $('#gcb-clear-index > input[name=xsrf_token]').attr('value');
  $.post('dashboard?action=clear_index',
         { xsrf_token: token },
         function(data) {
           var response = JSON.parse(data.replace(")]}'\n", ''));
           cbShowMsg(response.message);
         }, 'text');
  event.preventDefault();
}

$(function() {
  $('form#gcb-index-course > button').click(indexDocs);
  $('form#gcb-clear-index > button').click(clearIndex);
});
