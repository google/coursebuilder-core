# Copyright 2012 Google Inc. All Rights Reserved.
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

"""Schema for Announcements."""

__author__ = 'Pavel Simakov (psimakov@google.com)'

import json

# TODO(psimakov): we should really use an ordered dictionary, not plain text; it
# can't be just a normal dict because a dict iterates its items in undefined
# order;  thus when we render a dict to JSON an order of fields will not match
# what we specify here; the final editor will also show the fields in an
# undefined order; for now we use the raw JSON, rather than the dict, but will
# move to an ordered dict later
SCHEMA_JSON = """
    {
        "id": "Announcement Entity",
        "type": "object",
        "description": "Announcement",
        "properties": {
            "title": {"optional": true, "type": "string"},
            "date": {"optional": true, "type": "date"},
            "html": {"optional": true, "type": "text"},
            "is_draft": {"type": "boolean"}
            }
    }
    """

SCHEMA_DICT = json.loads(SCHEMA_JSON)

# inputex specific schema annotations to control editor look and feel
SCHEMA_ANNOTATIONS_DICT = [
    (['title'], 'Announcement'),
    (['properties', 'date', '_inputex'], {
        '_type': 'date', 'dateFormat': 'Y/m/d', 'valueFormat': 'Y/m/d',
        'label': 'Date'}),
    (['properties', 'title', '_inputex'], {'label': 'Title'}),
    (['properties', 'html', '_inputex'], {'_type': 'text', 'label': 'Body'}),
    (['properties', 'is_draft', '_inputex'], {'label': 'Is Draft'})
]
