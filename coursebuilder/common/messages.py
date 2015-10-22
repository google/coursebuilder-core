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

"""Messages used in common."""

__author__ = [
    'johncox@google.com (John Cox)',
]


SITE_SETTINGS_CACHE_TEMPLATES = """
If "True", Jinja2 can cache bytecode of compiled templates in-process. During
course development you should turn this setting to "False" so you can see your
changes instantaneously. Otherwise, keep this setting at "True" to maximize
performance.
"""

SITE_SETTINGS_DYNAMIC_TAGS = """
If "True", lesson content can use custom HTML tags such as <gcb-youtube
videoid="...">. If this setting is enabled, some legacy content may be rendered
differently.
"""

SITE_SETTINGS_ENCRYPTION_SECRET = """
Specify text used to encrypt messages. You can set this to any text at all, but
the value must be exactly 48 characters long. If you change this value, the
server will be unable to understand items encrypted under the old key.
"""

SITE_SETTINGS_XSRF_SECRET = """
Specify the text used to encrypt tokens, which help prevent cross-site request
forgery (XSRF). You can set the value to any alphanumeric text, preferably using
16-64 characters. Once you change this value, the server rejects all subsequent
requests issued using an old value for this variable.
"""
