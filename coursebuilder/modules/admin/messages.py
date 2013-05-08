# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Messages used in the admin panel."""

__author__ = 'John Orr (jorr@google.com)'

from common import safe_dom


def assemble_sanitized_message(text, link):
    node_list = safe_dom.NodeList()
    if text:
        node_list.append(safe_dom.Text(text))
    if link:
        node_list.append(safe_dom.Element(
            'a', href=link, target='_blank').add_text('Learn more...'))
    return node_list


COURSES_DESCRIPTION = assemble_sanitized_message(
    None, 'https://code.google.com/p/course-builder/wiki/CreateNewCourse')

DEPLOYMENT_DESCRIPTION = assemble_sanitized_message("""
These deployment settings are configurable by editing the Course Builder code
before uploading it to Google App Engine.
""", 'https://code.google.com/p/course-builder/wiki/AdminPage')

METRICS_DESCRIPTION = assemble_sanitized_message(
    None, 'https://code.google.com/p/course-builder/wiki/AdminPage')

SETTINGS_DESCRIPTION = assemble_sanitized_message(
    None, 'https://code.google.com/p/course-builder/wiki/AdminPage')
