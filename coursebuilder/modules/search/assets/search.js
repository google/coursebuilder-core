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
 * Utils for full text search
 *
 * @author: emichael@google.com (Ellis Michael)
 */

// requires jQuery (>= 1.7.2)


function submitOnEnter(evt, input) {
  var keyCode = evt.keyCode;
  if (keyCode == 13) {
    $(input).closest('form').submit();
    return false;
  }
  else {
    return true;
  }
}

$(function() {
  $('input.gcb-search-box').keypress(function(evt) {
    submitOnEnter(evt, 'input.gcb-search-box');
  });
  $('.gcb-search-result.youtube img').click(function() {
    if ($(this).hasClass('shown')) {
      $(this).addClass('hidden').removeClass('shown');
    }
    $(this).siblings('iframe').addClass('shown').removeClass('hidden');
  });
});
