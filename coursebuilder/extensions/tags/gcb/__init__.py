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
from models import courses
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
        reg = schema_fields.FieldRegistry('YouTube Video')
        reg.add_property(
            schema_fields.SchemaField('videoid', 'Video Id', 'string',
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
        return '/extensions/tags/gcb/resources/forumembed.png'

    def get_schema(self, unused_handler):
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


class Activity(tags.BaseTag):
    def render(self, node):
        activity_id = node.attrib.get('activityid')
        script = etree.XML("""
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
