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

"""Messages used in the mapreduce module."""

__author__ = [
    'johncox@google.com (John Cox)',
]

from common import safe_dom


SITE_SETTINGS_MAPREDUCE = safe_dom.NodeList().append(
    safe_dom.Element('div').add_text("""
If "True", you can access status pages for individual map/reduce jobs as they
run. These pages can also be used to cancel jobs. You may want to cancel huge
jobs that are consuming too many resources.
""")
).append(
    safe_dom.Element('br')
).append(
    safe_dom.Element('div').add_child(
        safe_dom.A(
            '/mapreduce/ui/pipeline/list', target='_blank'
        ).add_text(
            "See an example page (with this control enabled)"
        )
    )
)
