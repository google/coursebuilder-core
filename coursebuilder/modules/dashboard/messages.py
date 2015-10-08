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

"""Messages used in the dashboard."""

__author__ = 'John Orr (jorr@google.com)'

from common import safe_dom

ROLES_DESCRIPTION = """
Manage the different roles associated with your course.
A role binds a set of permissions to a set of users. The role editor allows you
to assign any of the permissions currently registered by the enabled modules.
"""

LABELS_TYPE_DESCRIPTION = """
You can put students in different <b>Course tracks</b> to show them different
units.
"""

GIFT_GROUP_DESCRIPTION_DESCRIPTION = """
This is the description of the question group created for the imported
questions.
"""

# TODO(tlarsen): Per Notes in http://b/24176227 spreadsheet:
#   "Learn more..." links to the docs (tbd)
GIFT_QUESTIONS_DESCRIPTION = safe_dom.assemble_text_message("""
Each question is imported as a separate question (named Q1, Q2, etc.).
Additionally, a question group is added with all the questions. Course Builder
supports multiple choice, true-false, short answer, and numerical questions.
""", "https://code.google.com/p/course-builder/wiki/Dashboard")
