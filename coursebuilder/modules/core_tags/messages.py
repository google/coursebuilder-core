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


RTE_GOOGLE_GROUP_CATEGORY_NAME = """
This is the name of the Google Group Category, if any was set up.
"""

RTE_GOOGLE_GROUP_GROUP_NAME = """
This is the name of the Google Group. The group must be @googlegroups.com.
"""

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

RTE_MARKDOWN_MARKDOWN = """
This is the markdown text.
"""

DOCUMENT_LINK_DESCRIPTION = """
This is the link from the Google Docs "Publish to the web" dialog to embed the
document.
"""

DOCUMENT_HEIGHT_DESCRIPTION = """
The document displays with this height; the width is set automatically.
"""

GOOGLE_DRIVE_UNAVAILABLE = """
Before embedding a Google Drive object, Google APIs must be configured for this
course.
"""

DOCUMENT_ID_DESCRIPTION = """
Paste the ID of the Google Drive item you want to use or pick one in the
chooser.
"""

VIDEO_ID_DESCRIPTION = """
This is the YouTube video ID (e.g., Kdg2drcUjYI) to embed.
"""

HTML5_VIDEO_URL_DESCRIPTION = """
This is the video to embed. Google Drive videos can be played by adding "&export=download" to the URL.
"""

HTML5_VIDEO_WIDTH_DESCRIPTION = """
The video displays with this width.
"""

HTML5_VIDEO_HEIGHT_DESCRIPTION = """
The video displays with this height.
"""

GOOGLE_SPREADSHEET_LINK_DESCRIPTION = """
This is the link from the Google Spreadsheet "Publish to the web" dialog to
embed the document.
"""

GOOGLE_SPREADSHEET_HEIGHT_DESCRIPTION = """
The document displays with this height; the width is set automatically.
"""

HTML_ASSET_FILE_PATH_DESCRIPTION = """
The path to an HTML file (e.g., "assets/html/example.html"). The contents of
that file will be inserted verbatim at this point. You can upload HTML files to
assets/html in Create > HTML.
"""
