# Copyright 2014 Google Inc. All Rights Reserved.
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

"""Core custom tags."""

__author__ = 'John Orr (jorr@google.com)'

import os
import re
import urllib
import urlparse
from xml.etree import cElementTree
import markdown

import appengine_config
from common import jinja_utils
from common import schema_fields
from common import tags
from common import utils as common_utils
from controllers import utils
from models import custom_modules


RESOURCE_FOLDER = '/modules/core_tags/resources/'


def _escape_url(url, force_https=True):
    """Escapes/quotes url parts to sane user input."""
    scheme, netloc, path, query, unused_fragment = urlparse.urlsplit(url)
    if force_https:
        scheme = 'https'
    path = urllib.quote(path)
    query = urllib.quote_plus(query, '=?&;')
    return urlparse.urlunsplit((scheme, netloc, path, query, unused_fragment))


def _replace_url_query(url, new_query):
    """Replaces the query part of a URL with a new one."""
    scheme, netloc, path, _, fragment = urlparse.urlsplit(url)
    return urlparse.urlunsplit((scheme, netloc, path, new_query, fragment))


class CoreTag(tags.BaseTag):
    """All core custom tags derive from this class."""

    @classmethod
    def vendor(cls):
        return 'gcb'

    @classmethod
    def create_icon_url(cls, name):
        """Creates a URL for an icon with a specific name."""
        return os.path.join(RESOURCE_FOLDER, name)


class GoogleDoc(CoreTag):
    """Custom tag for a Google Doc."""

    @classmethod
    def name(cls):
        return 'Google Doc'

    def render(self, node, unused_handler):
        height = node.attrib.get('height') or '300'
        link = node.attrib.get('link')
        url = _escape_url(_replace_url_query(link, 'embedded=true'))
        iframe = cElementTree.XML("""
<iframe class="google-doc" title="Google Doc" type="text/html" frameborder="0">
</iframe>""")
        iframe.set('src', url)
        iframe.set('style', 'width: %spx; height: %spx' % (700, height))
        return iframe

    def get_icon_url(self):
        return self.create_icon_url('docs.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(GoogleDoc.name())
        reg.add_property(
            # To get this value, users do File > Publish to the web..., click
            # 'Start publishing', and then copy and paste the Document link.
            # Changes to the publication status of a document or to its
            # contents do not appear instantly.
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


class GoogleSpreadsheet(CoreTag):
    """Custom tag for a Google Spreadsheet."""

    @classmethod
    def name(cls):
        return 'Google Spreadsheet'

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
        return self.create_icon_url('spreadsheets.png')

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


class YouTube(CoreTag):

    @classmethod
    def name(cls):
        return 'YouTube Video'

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
<div class="gcb-video-container">
  <iframe class="youtube-player" title="YouTube Video Player"
    type="text/html" frameborder="0" allowfullscreen="allowfullscreen">
  </iframe>
</div>""")
        iframe[0].set('src', you_tube_url)
        return iframe

    def _render_with_tracking(self, video_id):
        """Embed video and enable event tracking."""
        video_id = jinja_utils.js_string_raw(video_id)
        uid = common_utils.generate_instance_id()
        dom = cElementTree.XML("""
<p>
    <script></script>
    <script></script>
</p>""")
        dom.attrib['id'] = uid
        dom[0].attrib['src'] = os.path.join(RESOURCE_FOLDER, 'youtube_video.js')
        dom[1].text = 'gcbTagYoutubeEnqueueVideo("%s", "%s");' % (video_id, uid)
        return dom

    def get_icon_url(self):
        return self.create_icon_url('youtube.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(YouTube.name())
        reg.add_property(schema_fields.SchemaField(
            'videoid', 'Video Id', 'string',
            optional=True,
            description='Provide YouTube video ID (e.g. Kdg2drcUjYI)'))
        return reg


class Html5Video(CoreTag):

    @classmethod
    def name(cls):
        return 'HTML5 Video'

    def render(self, node, unused_handler):
        if utils.CAN_PERSIST_TAG_EVENTS.value:
            tracking_text = (
                '<script src="' + os.path.join(
                    RESOURCE_FOLDER, 'html5_video.js') + '">' +
                '</script>' +
                '<script>' +
                '  gcbTagHtml5TrackVideo("%s");' % (
                    jinja_utils.js_string_raw(node.attrib.get('instanceid'))) +
                '</script>')
        else:
            tracking_text = ''
        video_text = (
            '<div>' +
            '  <video></video>'
            '%s' % tracking_text +
            '</div>')
        video = cElementTree.XML(video_text)
        video[0].set('id', node.attrib.get('instanceid'))
        video[0].set('src', node.attrib.get('url'))
        if node.attrib.get('width'):
            video[0].set('width', node.attrib.get('width'))
        if node.attrib.get('height'):
            video[0].set('height', node.attrib.get('height'))
        video[0].set('controls', 'true')
        return video

    def get_icon_url(self):
        return self.create_icon_url('html5-badge-h-solo.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(Html5Video.name())
        reg.add_property(
            schema_fields.SchemaField(
                'url', 'Video URL', 'url',
                optional=False,
                description='URL of the video.  Note that playing a video'
                'from Google Docs is supported; add "&export=download".  E.g.,'
                'https://docs.google.com/a/google.com/uc?authuser=0'
                '&id=0B82t9jeypLokMERMQ1g5Q3NFU1E&export=download'))
        reg.add_property(schema_fields.SchemaField(
            'width', 'Width', 'integer',
            optional=True,
            description='Width, in pixels.'))
        reg.add_property(schema_fields.SchemaField(
            'height', 'Height', 'integer',
            optional=True,
            description='Height, in pixels.'))
        return reg


class GoogleGroup(CoreTag):

    @classmethod
    def name(cls):
        return 'Google Group'

    def render(self, node, handler):
        # Note: in Firefox, this component requires a full hostname to work.
        # If you are working in the development environment and are accessing
        # this component at localhost, please replace 'localhost' with
        # '127.0.0.1' instead.
        _, netloc, _, _, _ = urlparse.urlsplit(handler.request.uri)

        parent_url_suffix = ''
        if (appengine_config.PRODUCTION_MODE or
            not netloc.startswith('localhost')):
            parent_url_suffix = (
                '&parenturl=%s' % urllib.quote(handler.request.uri, safe=''))

        group_name = node.attrib.get('group')
        category_name = node.attrib.get('category')
        embedded_forum_url = (
            'https://groups.google.com/forum/embed/?hl=en%s'
            '#!categories/%s/%s' % (
                parent_url_suffix,
                urllib.quote(group_name),
                urllib.quote(category_name)
            ))
        iframe = cElementTree.XML("""
<p>
  <iframe class="forum-embed" title="Google Group Embed"
    type="text/html" width="700" height="300" frameborder="0">
  </iframe>
</p>""")
        iframe[0].set('src', embedded_forum_url)
        return iframe

    def get_icon_url(self):
        return self.create_icon_url('forumembed.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(GoogleGroup.name())
        reg.add_property(schema_fields.SchemaField(
            'group', 'Group Name', 'string', optional=True,
            description='Name of the Google Group (e.g. mapping-with-google)'))
        reg.add_property(schema_fields.SchemaField(
            'category', 'Category Name', 'string', optional=True,
            description='Name of the Category (e.g. unit5-2-annotation)'))
        return reg


class IFrame(CoreTag):

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
        return self.create_icon_url('iframe.png')

    def get_schema(self, unused_handler):
        reg = schema_fields.FieldRegistry(IFrame.name())
        reg.add_property(schema_fields.SchemaField(
            'src', 'Source URL', 'string',
            optional=True,
            description='Provide source URL for iframe (including http/https)'))
        reg.add_property(schema_fields.SchemaField(
            'title', 'Title', 'string',
            optional=True,
            description='Provide title of iframe'))
        reg.add_property(schema_fields.SchemaField(
            'height', 'Height', 'string',
            optional=True,
            extra_schema_dict_values={'value': '400'},
            description=('Height of the iframe')))
        reg.add_property(schema_fields.SchemaField(
            'width', 'Width', 'string',
            optional=True,
            extra_schema_dict_values={'value': '650'},
            description=('Width of the iframe')))
        return reg


class Include(CoreTag):

    def render(self, node, handler):
        template_path = re.sub('^/+', '', node.attrib.get('path'))
        base_path = os.path.dirname(template_path)
        base_file = os.path.basename(template_path)
        handler.init_template_values(handler.app_context.get_environ())
        handler.template_value['base_path'] = base_path
        html_text = handler.render_template_to_html(
            handler.template_value, base_file,
            additional_dirs=[
                os.path.join(appengine_config.BUNDLE_ROOT, 'views'),
                appengine_config.BUNDLE_ROOT,
                os.path.join(appengine_config.BUNDLE_ROOT, base_path),
            ])
        return tags.html_string_to_element_tree(html_text)

    def get_icon_url(self):
        return self.create_icon_url('include.png')

    def get_schema(self, handler):
        expected_prefix = os.path.join(appengine_config.BUNDLE_ROOT,
                                       'assets/html')
        all_files = handler.app_context.fs.list(expected_prefix,
                                                include_inherited=True)
        select_data = []
        for name in all_files:
            if name.startswith(expected_prefix):
                name = name.replace(appengine_config.BUNDLE_ROOT, '')
                select_data.append((name, name.replace('/assets/html/', '')))

        reg = schema_fields.FieldRegistry(Include.name())
        reg.add_property(schema_fields.SchemaField(
            'path', 'File Path', 'string', optional=False,
            select_data=select_data,
            description='Select a file from within assets/html.  '
            'The contents of this file will be inserted verbatim '
            'at this point.  Note: HTML files for inclusion may '
            'also be uploaded as assets.'))
        return reg


class Markdown(tags.ContextAwareTag, CoreTag):

    @classmethod
    def name(cls):
        return 'Markdown'

    def get_icon_url(self):
        return self.create_icon_url('markdown.png')

    def render(self, node, context):
        html = markdown.markdown(node.attrib.get('markdown'))
        return cElementTree.fromstring(
            '<div class="gcb-markdown">%s</div>' % html)

    def rollup_header_footer(self, context):
        """Include markdown css only when markdown tag is present."""
        header = tags.html_string_to_element_tree(
            '<link href="%s/markdown.css" rel="stylesheet" '
            'type="text/css">' % RESOURCE_FOLDER)
        footer = tags.html_string_to_element_tree('')
        return (header, footer)

    def get_schema(self, handler):
        reg = schema_fields.FieldRegistry(Markdown.name())
        reg.add_property(schema_fields.SchemaField(
            'markdown', 'Markdown', 'text', optional=False,
            description='Provide '
            '<a target="_blank" '
            'href="http://daringfireball.net/projects/markdown/syntax">'
            'markdown</a> text'))
        return reg


custom_module = None


def register_module():
    """Registers this module in the registry."""

    custom_tags = [
        GoogleDoc, GoogleSpreadsheet, YouTube, Html5Video, GoogleGroup,
        IFrame, Include, Markdown]

    def make_binding_name(custom_tag):
        return 'gcb-%s' % custom_tag.__name__.lower()

    def on_module_disable():
        for custom_tag in custom_tags:
            tags.Registry.remove_tag_binding(make_binding_name(custom_tag))

    def on_module_enable():
        for custom_tag in custom_tags:
            tags.Registry.add_tag_binding(
                make_binding_name(custom_tag), custom_tag)

    global custom_module

    global_routes = [(
        os.path.join(RESOURCE_FOLDER, '.*'), tags.ResourcesHandler)]

    custom_module = custom_modules.Module(
        'Core Custom Tags Module',
        'A module that provides core custom tags.',
        global_routes, [],
        notify_module_enabled=on_module_enable,
        notify_module_disabled=on_module_disable)
    return custom_module
