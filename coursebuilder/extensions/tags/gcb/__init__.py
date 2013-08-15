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

import urllib
import urlparse
from common import jinja_utils
from common import schema_fields
from common import tags
from controllers import utils
from models import courses
from xml.etree import cElementTree


def _escape_url(url, force_https=True):
    """Escapes/quotes url parts to sane user input."""
    scheme, netloc, path, query, unused_fragment = urlparse.urlsplit(url)
    if force_https:
        scheme = 'https'
    path = urllib.quote(path)
    query = urllib.quote_plus(query, '=?&;')
    return urlparse.urlunsplit((scheme, netloc, path, query, unused_fragment))


class GoogleDoc(tags.BaseTag):
    """Custom tag for a Google Doc."""

    @classmethod
    def name(cls):
        return'Google Doc'

    def render(self, node, unused_handler):
        height = node.attrib.get('height') or '300'
        link = node.attrib.get('link')
        url = _escape_url('%s?embedded=true' % link)
        iframe = cElementTree.XML("""
<iframe class="google-doc" title="Google Doc" type="text/html" frameborder="0">
</iframe>""")
        iframe.set('src', url)
        iframe.set('style', 'width: %spx; height: %spx' % (700, height))
        return iframe

    def get_icon_url(self):
        return '/extensions/tags/gcb/resources/docs.png'

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(GoogleDoc.name())
        reg.add_property(
            # To get this value, users do File > Publish to the web..., click
            # 'Start publishing', and then copy and paste the Document link.
            # Changes to the publication status of a document or to its contents
            # do not appear instantly.
            schema_fields.SchemaField(
                'link', 'Document Link', 'string',
                optional=True,
                description=('Provide the "Document Link" from the Google Docs '
                             '"Publish to the web" dialog')))
        reg.add_property(
            schema_fields.SchemaField(
                'height', 'Height', 'string',
                optional=True,
                extra_schema_dict_values={'value': '300'},
                description=('Height of the document, in pixels. Width will be '
                             'set automatically')))
        return reg


class GoogleSpreadsheet(tags.BaseTag):
    """Custom tag for a Google Spreadsheet."""

    @classmethod
    def name(cls):
        return'Google Spreadsheet'

    def render(self, node, unused_handler):
        height = node.attrib.get('height') or '300'
        link = node.attrib.get('link')
        url = _escape_url('%s&amp;chrome=false' % link.split('&output')[0])
        iframe = cElementTree.XML("""
<iframe class="google-spreadsheet" title="Google Spreadsheet" type="text/html"
    frameborder="0">
</iframe>""")
        iframe.set('src', url)
        iframe.set('style', 'width: %spx; height: %spx' % (700, height))
        return iframe

    def get_icon_url(self):
        return '/extensions/tags/gcb/resources/spreadsheets.png'

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(GoogleSpreadsheet.name())
        reg.add_property(
            # To get this value, users do File > Publish to the web..., click
            # 'Start publishing', and then copy and paste the link above 'Copy
            # and paste the link above'. Changes to the publication status of a
            # document or to its contents do not appear instantly.
            schema_fields.SchemaField(
                'link', 'Link', 'string',
                optional=True,
                description=('Provide the link from the Google Spreadsheets '
                             '"Publish to the web" dialog')))
        reg.add_property(
            schema_fields.SchemaField(
                'height', 'Height', 'string',
                optional=True,
                extra_schema_dict_values={'value': '300'},
                description=('Height of the spreadsheet, in pixels. Width will '
                             'be set automatically')))
        return reg


class YouTube(tags.BaseTag):

    @classmethod
    def name(cls):
        return'YouTube Video'

    def render(self, node, unused_handler):
        video_id = node.attrib.get('videoid')
        if utils.CAN_PERSIST_TAG_EVENTS.value:
            return self._render_with_tracking(video_id)
        else:
            return self._render_no_tracking(video_id)

    def _render_no_tracking(self, video_id):
        """Embed video without event tracking support."""
        you_tube_url = (
            'https://www.youtube.com/embed/%s'
            '?feature=player_embedded&amp;rel=0') % video_id
        iframe = cElementTree.XML("""
<p class="gcb-video-container">
  <iframe class="youtube-player" title="YouTube Video Player"
    type="text/html" width="650" height="400" frameborder="0"
    allowfullscreen="allowfullscreen">
  </iframe>
</p>""")
        iframe[0].set('src', you_tube_url)
        return iframe

    def _render_with_tracking(self, video_id):
        """Embed video and enable event tracking."""
        video_id = jinja_utils.js_string_raw(video_id)
        return cElementTree.XML("""
<p>
    <script src='/extensions/tags/gcb/resources/youtube_video.js'></script>
    <script>
      gcbTagYoutubeEnqueueVideo('""" + video_id + """');
    </script>
</p>""")

    def get_icon_url(self):
        return '/extensions/tags/gcb/resources/youtube.png'

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(YouTube.name())
        reg.add_property(
            schema_fields.SchemaField('videoid', 'Video Id', 'string',
            optional=True,
            description='Provide YouTube video ID (e.g. Kdg2drcUjYI)'))
        return reg


class GoogleGroup(tags.BaseTag):

    @classmethod
    def name(cls):
        return 'Google Group'

    def render(self, node, unused_handler):
        group_name = node.attrib.get('group')
        category_name = node.attrib.get('category')
        embedded_forum_url = (
            'https://groups.google.com/forum/embed/?place=forum/?'
            'fromgroups&hl=en#!categories/%s/%s') \
            % (urllib.quote(group_name), urllib.quote(category_name))
        iframe = cElementTree.XML("""
<p>
  <iframe class="forum-embed" title="Google Group Embed"
    type="text/html" width="700" height="300" frameborder="0">
  </iframe>
</p>""")
        iframe[0].set('src', embedded_forum_url)
        return iframe

    def get_icon_url(self):
        return '/extensions/tags/gcb/resources/forumembed.png'

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(GoogleGroup.name())
        reg.add_property(
            schema_fields.SchemaField(
              'group', 'Group Name', 'string', optional=True,
              description='Name of the Google Group (e.g. mapping-with-google)'))
        reg.add_property(
            schema_fields.SchemaField(
              'category', 'Category Name', 'string', optional=True,
              description='Name of the Category (e.g. unit5-2-annotation)'))
        return reg


class IFrame(tags.BaseTag):

    def render(self, node, unused_handler):
        src = node.attrib.get('src')
        title = node.attrib.get('title')
        height = node.attrib.get('height') or '400'
        width = node.attrib.get('width') or '650'

        iframe = cElementTree.XML(
            '<iframe style="border: 0;"></iframe>'
        )

        iframe.set('src', _escape_url(src, force_https=False))
        iframe.set('title', title)
        iframe.set('width', width)
        iframe.set('height', height)
        return iframe

    def get_icon_url(self):
        """Return the URL for the icon to be displayed in the rich text editor.

        Images should be placed in a folder called 'resources' inside the main
        package for the tag definitions."""

        return '/extensions/tags/gcb/resources/iframe.png'

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(IFrame.name())
        reg.add_property(
            schema_fields.SchemaField('src', 'Source URL', 'string',
            optional=True,
            description='Provide source URL for iframe (including http/https)'))
        reg.add_property(
            schema_fields.SchemaField('title', 'Title', 'string',
            optional=True,
            description='Provide title of iframe'))
        reg.add_property(
            schema_fields.SchemaField(
                'height', 'Height', 'string',
                optional=True,
                extra_schema_dict_values={'value': '400'},
                description=('Height of the iframe')))
        reg.add_property(
            schema_fields.SchemaField(
                'width', 'Width', 'string',
                optional=True,
                extra_schema_dict_values={'value': '650'},
                description=('Width of the iframe')))
        return reg
