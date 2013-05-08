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

"""GCB-provided custom tags."""

__author__ = 'John Orr (jorr@google.com)'

from common import tags
from lxml import etree


class YouTube(tags.BaseTag):
    def render(self, node):
        video_id = node.attrib.get('videoid')
        you_tube_url = (
            'https://www.youtube.com/embed/%s'
            '?feature=player_embedded&amp;rel=0') % video_id
        iframe = etree.XML("""
<p class="video-container">
  <iframe class="youtube-player" title="YouTube Video Player"
    type="text/html" width="650" height="400" frameborder="0"
    allowfullscreen="allowfullscreen">
  </iframe>
</p>""")
        iframe[0].set('src', you_tube_url)
        return iframe

    def get_icon_url(self):
        return """
data:image/png;base64,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
ykXhHPKj8AAAAASUVORK5CYII=
"""
