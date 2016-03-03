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

""" Help text and other strings used in the Drive module. """

__author__ = [
    'nretallack@google.com (Nick Retallack)',
]

SERVICE_ACCOUNT_JSON_DESCRIPTION = """
Create a service account in Google App Engine and paste the JSON here.
"""

SERVICE_ACCOUNT_JSON_PARSE_FAILURE = """
The JSON is invalid.  Make sure you copy the whole thing including any curly
braces.  Do not use the P12 format."""

SERVICE_ACCOUNT_JSON_MISSING_FIELDS = """
The JSON is valid but it doesn't look like a service account key. Try creating a
new "Service account key" in the Credentials section of the developer console.
You can only download this JSON when you first create the key.  You can't use
the "Download JSON" button later as this will not include the key."""

SYNC_FREQUENCY_DESCRIPTION = """
The document will be checked for changes in Google Drive this often.
"""

AVAILABILITY_DESCRIPTION = """
Synced items default to the availability of the course, but may also be
restricted to admins (Private) or open to the public (Public).
"""

SHARE_PERMISSION_ERROR = """
You do not have permission to share this file.
"""

SHARE_UNKNOWN_ERROR = """
An unknown error occurred when sharing this file.  Check your Drive or Google
API configuration or try again.
"""

SHARE_META_ERROR = """
File shared, but Drive API failed to fetch metadata.  Please try again or check
your Drive configuration.
"""

TIMEOUT_ERROR = """
Google Drive timed out.  Please try again.
"""
