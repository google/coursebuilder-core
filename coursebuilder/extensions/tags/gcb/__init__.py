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
import urlparse
from common import schema_fields
from common import tags
from models import courses
from xml.etree import cElementTree


def _escape_url(url):
    """Escapes/quotes url parts to sane user input; force https."""
    scheme, netloc, path, query, unused_fragment = urlparse.urlsplit(url)
    scheme = 'https'
    path = urllib.quote(path)
    query = urllib.quote_plus(query, '=?&;')
    return urlparse.urlunsplit((scheme, netloc, path, query, unused_fragment))


class GoogleDoc(tags.BaseTag):
    """Custom tag for a Google Doc."""

    @classmethod
    def name(cls):
        return'Google Doc'

    def render(self, node):
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

    def render(self, node):
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

    def render(self, node):
        video_id = node.attrib.get('videoid')
        you_tube_url = (
            'https://www.youtube.com/embed/%s'
            '?feature=player_embedded&amp;rel=0') % video_id
        iframe = cElementTree.XML("""
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

        Images should be placed in a folder called 'resources' inside the main
        package for the tag definitions."""

        return '/extensions/tags/gcb/resources/youtube.png'

    def get_schema(self, unused_handler):
        """Return the list of fields which will be displayed in the editor.

        This method assembles the list of fields which will be displayed in
        the rich text editor when a user double-clicks on the icon for the tag.
        The fields are a list of SchemaField objects in a FieldRegistry
        container. Each SchemaField has the actual attribute name as used in the
        tag, the display name for the form, and the type (usually string)."""
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

    def render(self, node):
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


class Activity(tags.BaseTag):

    def render(self, node):
        activity_id = node.attrib.get('activityid')
        script = cElementTree.XML("""
<div>
  <script></script>
  <div style="width: 785px;" id="activityContents"></div>
</div>""")
        script[0].set('src', 'assets/js/%s' % activity_id)
        return script

    def get_icon_url(self):
        return '/extensions/tags/gcb/resources/activity.png'

    def get_schema(self, handler):
        course = courses.Course(handler)

        lesson_id = handler.request.get('lesson_id')

        activity_list = []
        for unit in course.get_units():
            for lesson in course.get_lessons(unit.unit_id):
                filename = 'activity-%s.js' % lesson.lesson_id
                if lesson.has_activity:
                    if lesson.activity_title:
                        title = lesson.activity_title
                    else:
                        title = filename
                    name = '%s - %s (%s) ' % (unit.title, lesson.title, title)
                    activity_list.append((filename, name))
                elif str(lesson.lesson_id) == lesson_id:
                    name = 'Current Lesson (%s)' % filename
                    activity_list.append((filename, name))

        reg = schema_fields.FieldRegistry('Activity')
        reg.add_property(
            schema_fields.SchemaField(
              'activityid', 'Activity Id', 'select', optional=True,
              select_data=activity_list,
              description=(
                  'The ID of the activity (e.g. activity-2.4.js). '
                  'Note /assets/js/ is not required')))
        return reg

