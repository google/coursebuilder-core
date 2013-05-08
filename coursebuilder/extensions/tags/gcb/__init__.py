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

__author__ = 'John Orr (jorr@google.com)', 'Aparna Kadakia (akadakia@google.com)'

import urllib
from common import schema_fields
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
        """Return the URL for the icon to be displayed in the rich text editor.

        In this example, the icon is encoded into the URL using the 'data'
        production, but the URL could equally well point to the location of
        an image file hosted on the server."""

        return """
data:image/png;base64,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
ykXhHPKj8AAAAASUVORK5CYII=
"""

    def get_schema(self):
        """Return the list of fields which will be displayed in the editor.

        This method assembles the list of fields which will be displayed in
        the rich text editor when a user double-clicks on the icon for the tag.
        The fields are a list of SchemaField objects in a FieldRegistry
        container. Each SchemaField has the actual attribute name as used in the
        tag, the display name for the form, and the type (usually string)."""
        reg = schema_fields.FieldRegistry('YouTube Video')
        reg.add_property(
            schema_fields.SchemaField('videoid', 'VideoId', 'string',
            optional=True,
            description='Provide YouTube video ID (e.g. Kdg2drcUjYI)'))
        return reg


class ForumEmbed(tags.BaseTag):
    def render(self, node):
        forum_name = node.attrib.get('forum')
        category_name = node.attrib.get('category')
        embedded_forum_url = (
            'https://groups.google.com/forum/embed/?place=forum/?'
            'fromgroups&hl=en#!categories/%s/%s') \
            % (urllib.quote(forum_name), urllib.quote(category_name))
        iframe = etree.XML("""
<p>
  <iframe class="forum-embed" title="Forum Embed"
    type="text/html" width="700" height="300" frameborder="0">
  </iframe>
</p>""")
        iframe[0].set('src', embedded_forum_url)
        return iframe

    def get_icon_url(self):
        """Return the URL for the icon to be displayed in the rich text editor.

        In this example, the icon is encoded into the URL using the 'data'
        production, but the URL could equally well point to the location of
        an image file hosted on the server."""

        return """
data:image/jpeg;base64,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
AAAAAAAAAAAAAAAAAAAAAAAAAP/2Q==
"""

    def get_schema(self):
        """Return the list of fields which will be displayed in the editor.

        This method assembles the list of fields which will be displayed in
        the rich text editor when a user double-clicks on the icon for the tag.
        The fields are a list of SchemaField objects in a FieldRegistry
        container. Each SchemaField has the actual attribute name as used in the
        tag, the display name for the form, and the type (usually string)."""
        reg = schema_fields.FieldRegistry('Forum')
        reg.add_property(
            schema_fields.SchemaField(
              'forum', 'Forum Name', 'string', optional=True,
              description='Name of the Forum (e.g. mapping-with-google)'))
        reg.add_property(
            schema_fields.SchemaField(
              'category', 'Category Name', 'string', optional=True,
              description='Name of the Category (e.g. unit5-2-annotation)'))
        return reg

