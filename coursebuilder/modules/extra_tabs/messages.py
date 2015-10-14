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

"""Messages used by extra tabs pages."""

__author__ = 'Todd Larsen (tlarsen@google.com)'

EXTRA_TABS_DESCRIPTION = """
Extra tabs appear on the course navbar.
"""

EXTRA_TABS_TITLE_DESCRIPTION = """
This is the name of this tab displayed on the course navbar.
"""

EXTRA_TAB_POSITION_DESCRIPTION = """
This indicates if this tab is right or left aligned. Tabs aligned on the same
side are displayed in the order added here.
"""

EXTRA_TABS_VISIBILITY_DESCRIPTION = """
This indicates if this tab is visible to everyone or only registered students.
"""

EXTRA_TABS_URL_DESCRIPTION = """
If a URL is provided, this tab will link to that URL. Otherwise, it will
display the "Tab Content" in a page. Links to other sites must start with
"http" or "https".
"""

EXTRA_TABS_CONTENT_DESCRIPTION = """
This content will be displayed on a page accessed from the tab. If the
"Tab URL" is provided, that will be used instead.
"""
