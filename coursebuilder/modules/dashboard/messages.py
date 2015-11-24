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

LABELS_TITLE_DESCRIPTION = """
This is the name of this label.
"""

LABELS_DESCRIPTION_DESCRIPTION = """
This is the description of this label.
"""

TRACKS_TITLE_DESCRIPTION = """
This is the name of this track.
"""

TRACKS_DESCRIPTION_DESCRIPTION = """
This is the description of this track.
"""

GIFT_GROUP_DESCRIPTION_DESCRIPTION = """
This is the description of the question group created for the imported
questions.
"""

GIFT_QUESTIONS_DESCRIPTION = """
Each question is imported as a separate question (named Q1, Q2, etc.).
Additionally, a question group is added with all the questions. Course Builder
supports multiple choice, true-false, short answer, and numerical questions.
"""

IMAGES_DOCS_UPLOAD_NEW_FILE_DESCRIPTION = """
Upload a file to set or replace the content of this asset.
"""

IMAGES_DOCS_UPLOAD_NEW_CSS_DESCRIPTION = """
Upload a new CSS file, which must not have the same name as any existing CSS
file.<br>
To edit an existing CSS file, select it from the previous
""" + str(safe_dom.assemble_link(
    "dashboard?action=style_css", "Style > CSS",
    title="Opens the Style > CSS list in a new browser tab.",
    target="_blank")) + """
list.
"""

IMAGES_DOCS_UPLOAD_NEW_HTML_DESCRIPTION = """
Upload a new HTML file, which must not have the same name as any existing
HTML file.<br>
To edit an existing HTML file, select it from the previous
""" + str(safe_dom.assemble_link(
    "dashboard?action=edit_html", "Create > HTML",
    title="Opens the Create > HTML list in a new browser tab.",
    target="_blank")) + """
list.
"""

IMAGES_DOCS_UPLOAD_NEW_JS_DESCRIPTION = """
Upload a new JavaScript file, which must not have the same name as any
existing JavaScript file.<br>
To edit an existing JavaScript file, select it from the previous
""" + str(safe_dom.assemble_link(
    "dashboard?action=style_js", "Style > JavaScript",
    title="Opens the Style > JavaScript list in a new browser tab.",
    target="_blank")) + """
list.
"""

IMAGES_DOCS_UPLOAD_NEW_TEMPLATE_DESCRIPTION = """
Upload a new HTML template, which must not have the same name as any existing
HTML template.<br>
To edit an existing HTML template, select it from the previous
""" + str(safe_dom.assemble_link(
    "dashboard?action=style_templates", "Style > Templates",
    title="Opens the Style > Templates list in a new browser tab.",
    target="_blank")) + """
list.
"""

IMAGES_DOCS_UPLOAD_NEW_IMAGE_DESCRIPTION = """
Upload an image to set or replace the content of this asset.
"""

ROLE_NAME_DESCRIPTION = """
This is the name of this role.
"""

ROLE_DESCRIPTION_DESCRIPTION = """
This describes this role for your reference.
"""

ROLE_USER_EMAILS_DESCRIPTION = """
This list of email addresses represents the members of this role.
Separate addresses with a comma, space, or newline.
"""
