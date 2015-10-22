# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Messages used in the core_tags module."""

__author__ = [
    'johncox@google.com (John Cox)',
]

from common import safe_dom


RTE_GOOGLE_GROUP_CATEGORY_NAME = """
This is the name of the Google Group Category, if any was set up.
"""

# TODO(johncox): replace placeholder URL once target link is determined.
RTE_GOOGLE_GROUP_GROUP_NAME = safe_dom.assemble_text_message("""
This is the name of the Google Group.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard')

RTE_IFRAME_EMBED_URL = """
This is the URL to be embedded as an iframe. Links to other sites must start with "https".
"""

RTE_IFRAME_HEIGHT = """
This is the height of the iframe, in pixels.
"""

RTE_IFRAME_TITLE = """
This is used for the "title" parameter of the iframe.
"""

RTE_IFRAME_WIDTH = """
This is the width of the iframe, in pixels.
"""

# TODO(johncox): replace placeholder URL once target link is determined.
RTE_MARKDOWN_MARKDOWN = safe_dom.assemble_text_message("""
This is the markdown text.
""", 'https://code.google.com/p/course-builder/wiki/Dashboard')
